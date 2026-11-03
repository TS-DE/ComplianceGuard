"""DashScope 网络适配与 Chroma 持久化适配，禁止默认模型下载。"""
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
EMBED_BATCH_SIZE = 25
EMBED_DIMENSIONS = 1024
EMBED_MODEL = 'text-embedding-v3'
DASHSCOPE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
JUDGE_TIMEOUT = int(os.getenv("JUDGE_TIMEOUT", "180"))
NETWORK_TIMEOUT = JUDGE_TIMEOUT  # 兼容旧import；urllib为单次阻塞读操作超时，非总时长上限。


from backend.core.errors import ModelCallError, model_error


class EmbeddingError(ModelCallError):
    """明确表示向量服务不可用，调用方必须降级并留状态。"""


def llm_config():
    """读取本地配置及环境变量；不打印任何密钥值。"""
    return {**dotenv_values(ROOT / '.env'), **os.environ}


class DashScopeEmbeddingFunction:
    """自定义 1024 维 embedding；transport 可注入以隔离网络测试。"""

    def __init__(self, api_key=None, transport=None):
        config = llm_config()
        self.timeout = int(config.get("JUDGE_TIMEOUT", JUDGE_TIMEOUT))
        self.api_key = api_key or config.get('JUDGE_API_KEY')
        self.base_url = config.get('JUDGE_BASE_URL', DASHSCOPE_URL).rstrip('/')
        self.model = config.get('EMBEDDING_MODEL', EMBED_MODEL)
        if self.model != EMBED_MODEL:
            raise EmbeddingError('现有索引仅允许 text-embedding-v3，换模型必须重建')
        self.batch_size = min(EMBED_BATCH_SIZE, int(config.get('EMBEDDING_BATCH_SIZE', 10)))
        if self.batch_size < 1:
            raise EmbeddingError('EMBEDDING_BATCH_SIZE 必须为正整数')
        self.transport = transport or self._request

    @staticmethod
    def name():
        return 'dashscope-text-embedding-v3'

    def _request(self, path, payload):
        """请求兼容端点；异常只包含状态码，不回显响应或密钥。"""
        if not self.api_key:
            raise EmbeddingError('缺少 JUDGE_API_KEY；请在本地 .env 配置')
        config=llm_config()
        if path == '/chat/completions' and str(config.get('JUDGE_PASS_THINKING_PARAM','true')).lower()=='true' and 'EMBEDDING_ENABLE_THINKING' in config:
            payload=dict(payload,enable_thinking=str(config['EMBEDDING_ENABLE_THINKING']).lower()=='true')
        request = Request(self.base_url + path, data=json.dumps(payload).encode('utf-8'),
                          headers={'Authorization': f'Bearer {self.api_key}',
                                   'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
                record_usage(path, payload, llm_config())
                return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            error=model_error(exc,self.timeout,'向量/改写服务')
            raise EmbeddingError(str(error),error.kind,error.attempt_limit) from None

    def __call__(self, input):
        """接受文本列表；input 命名遵循 Chroma 协议，批量不超过 25。"""
        documents = list(input)
        vectors = []
        for start in range(0, len(documents), self.batch_size):
            batch = documents[start:start + self.batch_size]
            response = self.transport('/embeddings', {'model': EMBED_MODEL,
                                      'input': batch, 'dimensions': EMBED_DIMENSIONS})
            try:
                rows = sorted(response['data'], key=lambda row: row['index'])
                if [row['index'] for row in rows] != list(range(len(batch))):
                    raise ValueError('indices')
                values = [row['embedding'] for row in rows]
                if any(len(v) != EMBED_DIMENSIONS or not all(math.isfinite(x) for x in v)
                       for v in values):
                    raise ValueError('dimensions')
            except (KeyError, TypeError, ValueError):
                raise EmbeddingError('DashScope 向量数量、维度或数值不合法') from None
            vectors.extend(values)
        return vectors

    def embed_query(self, input):
        return self(input)

    def get_config(self):
        return {'model': EMBED_MODEL, 'dimensions': EMBED_DIMENSIONS}


class ChromaStore:
    """向量存储适配；仅该基础设施模块直接依赖 Chroma。"""

    def __init__(self, path=None, embedding=None):
        import chromadb
        self.embedding = embedding or DashScopeEmbeddingFunction()
        self.client = chromadb.PersistentClient(path=str(path or ROOT / 'data/chroma'))
        self.collections = {}
        for name in ('law_articles', 'case_fines'):
            self.collections[name] = self.client.get_or_create_collection(
                name, embedding_function=self.embedding, metadata={'hnsw:space': 'cosine',
                'embedding_model': EMBED_MODEL, 'dimensions': EMBED_DIMENSIONS})

    def upsert(self, name, records):
        """稳定 ID 覆盖；向量生成失败时不伪造入库成功。"""
        for start in range(0, len(records), EMBED_BATCH_SIZE):
            batch = records[start:start + EMBED_BATCH_SIZE]
            vectors = self.embedding([row['text'] for row in batch])
            self.collections[name].upsert(ids=[row['id'] for row in batch],
                documents=[row['text'] for row in batch],
                metadatas=[row['metadata'] for row in batch], embeddings=vectors)

    def query(self, name, text, k, where=None):
        """以远程向量查询；结果为稳定 ID 顺序。"""
        collection = self.collections[name]
        if not collection.count():
            raise EmbeddingError(f'{name} 尚未建立向量索引')
        result = collection.query(query_embeddings=self.embedding([text]),
                                  n_results=min(k, collection.count()), where=where)
        return result['ids'][0]

    def count(self, name):
        return self.collections[name].count()


# 请求级用量上下文，只记录实际响应token，不发起额外网络请求。
from contextvars import ContextVar
from contextlib import contextmanager
from backend.core.constants import compute_cost, add_cost, MODEL_PRICES

_USAGE = ContextVar('rag_usage',default=None)


@contextmanager
def usage_meter():
    """隔离每次审查的RAG费用，不污染并行请求。"""
    values={k:dict(prompt_tokens=0,completion_tokens=0,cost=0,calls=0) for k in ('rag_rewrite','embedding')}
    token=_USAGE.set(values)
    try:
        yield values
    finally:
        _USAGE.reset(token)


def record_usage(path, response, config):
    """记录服务响应费用；缺token或单价为未知，不冒充零。"""
    values=_USAGE.get()
    if values is None: return
    usage=response.get('usage',{})
    kind='embedding' if path=='/embeddings' else 'rag_rewrite'
    if kind=='embedding':
        prompt=usage.get('total_tokens',usage.get('prompt_tokens'))
        completion=0
        price_in=config.get('EMBEDDING_PRICE_PER_M') or None
        price_out=0
    else:
        prompt,completion=usage.get('prompt_tokens'),usage.get('completion_tokens')
        fallback=MODEL_PRICES.get(config.get('JUDGE_MODEL'),{})
        price_in=config.get('JUDGE_INPUT_PRICE_PER_M') or fallback.get('in')
        price_out=config.get('JUDGE_OUTPUT_PRICE_PER_M') or fallback.get('out')
    cost=compute_cost(prompt,completion,price_in,price_out) if prompt is not None and completion is not None else None
    row=values[kind]
    row['prompt_tokens']+=prompt or 0
    row['completion_tokens']+=completion or 0
    row['calls']+=1
    row['cost']=add_cost(row['cost'],cost)
