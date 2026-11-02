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
NETWORK_TIMEOUT = 30


class EmbeddingError(RuntimeError):
    """明确表示向量服务不可用，调用方必须降级并留状态。"""


def llm_config():
    """读取本地配置及环境变量；不打印任何密钥值。"""
    return {**dotenv_values(ROOT / '.env'), **os.environ}


class DashScopeEmbeddingFunction:
    """自定义 1024 维 embedding；transport 可注入以隔离网络测试。"""

    def __init__(self, api_key=None, transport=None):
        self.api_key = api_key or llm_config().get('JUDGE_API_KEY')
        self.transport = transport or self._request

    @staticmethod
    def name():
        return 'dashscope-text-embedding-v3'

    def _request(self, path, payload):
        """请求兼容端点；异常只包含状态码，不回显响应或密钥。"""
        if not self.api_key:
            raise EmbeddingError('缺少 JUDGE_API_KEY；请在本地 .env 配置')
        request = Request(DASHSCOPE_URL + path, data=json.dumps(payload).encode('utf-8'),
                          headers={'Authorization': f'Bearer {self.api_key}',
                                   'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=NETWORK_TIMEOUT) as response:
                return json.load(response)
        except HTTPError as exc:
            raise EmbeddingError(f'DashScope HTTP {exc.code}') from None
        except (URLError, TimeoutError, ValueError, OSError):
            raise EmbeddingError('DashScope 请求失败或响应非法') from None

    def __call__(self, input):
        """接受文本列表；input 命名遵循 Chroma 协议，批量不超过 25。"""
        documents = list(input)
        vectors = []
        for start in range(0, len(documents), EMBED_BATCH_SIZE):
            batch = documents[start:start + EMBED_BATCH_SIZE]
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
