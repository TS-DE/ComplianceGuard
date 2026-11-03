"""审查组合根与 urllib 模型边界；数据库操作仅经仓储执行。"""
import json
from decimal import Decimal
from time import perf_counter
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.agents.base import ChatModel
from backend.core.config import DISCLAIMER_TEXT
from backend.core.constants import MODEL_PRICES, compute_cost, add_cost, to_refs
from backend.rag.embedding import DASHSCOPE_URL, NETWORK_TIMEOUT, EmbeddingError, llm_config

TOKENS_PER_MILLION = Decimal("1000000")
# 未指定报价时明确采用零报价，不声称这是供应商的实际收费。
DEFAULT_INPUT_PRICE = "0"
DEFAULT_OUTPUT_PRICE = "0"


def search_law(query, top_k=3):
    """复用 MCP 检索实现，延迟导入避免工具注册时循环依赖。"""
    from backend.mcp_server.server import rag_search_law
    return rag_search_law(query, top_k)


def indexed_docs():
    """只读本地 Chroma 元数据，不创建集合、不触发 embedding 或网络。"""
    import chromadb
    from backend.rag.embedding import ROOT
    collection = chromadb.PersistentClient(path=str(ROOT / 'data/chroma')).get_collection('law_articles')
    return {ref.rsplit('.', 1)[0] for row in collection.get(include=['metadatas'])['metadatas']
            for ref in to_refs(row['code'])}


class AuditTool:
    """组合审查、改写与仓储；API/MCP 共用相同 N1–N8 复核路径。"""

    def __init__(self, repository, model=None, search_law=search_law, detectors=None):
        """输入仓储、模型及检索 callable；不在业务编排内执行 SQL。"""
        from backend.agents.compliance import ComplianceAuditAgent, RewriteAgent
        self.repository = repository
        self.model = model if model is not None else UrllibChatModel()
        known = indexed_docs() if search_law is globals()["search_law"] else None
        self.auditor = ComplianceAuditAgent(repository.load_rules, search_law, self.model, detectors, known_docs=known,
            semantic_mode=__import__("os").environ.get("JUDGE_MODE", "merged") if known is not None else "multi")
        self.rewriter = RewriteAgent(self.auditor, self.model)

    def _client(self, client_id):
        """机构不存在报 404，None 表示不按机构限定。"""
        from backend.core.errors import NotFoundError
        if client_id is not None and not self.repository.client(client_id):
            raise NotFoundError("client", client_id)

    def run_audit(self, script_id, client_id):
        """读取原文、校验归属，完整审查后原子落库并返回结果。"""
        from backend.core.errors import NotFoundError, BusinessValidationError
        from backend.tools.db_tool import require_positive
        require_positive(script_id, "script_id")
        require_positive(client_id, "client_id")
        self._client(client_id)
        script = self.repository.script(script_id)
        if script is None:
            raise NotFoundError("script", script_id)
        if script["client_id"] != client_id:
            raise BusinessValidationError("话术不属于指定机构")
        started = perf_counter()
        result = self.auditor.review(script["content"], client_id=client_id)
        before = perf_counter()
        audit_id = self.repository.save(script_id, result)
        result.setdefault("timings_ms", {})["persist"] = (perf_counter() - before) * 1000
        result["latency_ms"] = int((perf_counter() - started) * 1000)
        if hasattr(self.repository, "update_latency"):
            self.repository.update_latency(audit_id, result["latency_ms"])
        logging.getLogger(__name__).warning("audit_timings_ms=%s", result["timings_ms"])
        result["llm_calls"] = getattr(self.model, "calls", [])
        return dict(result, id=audit_id, audit_id=audit_id, script_id=script_id)

    def rewrite_audit(self, audit_id):
        """以原话术与有效命中生成改写，复核后持久化状态。"""
        from backend.core.errors import NotFoundError
        from backend.tools.db_tool import require_positive
        require_positive(audit_id, "audit_id")
        audit = self.repository.audit(audit_id)
        if audit is None:
            raise NotFoundError("audit", audit_id)
        script = self.repository.script(audit["script_id"])
        hits = [hit for hit in audit["hits"] if hit.get("status", "active") == "active"]
        result = self.rewriter.rewrite(script["content"], hits, client_id=script["client_id"])
        # A2 返回的是生成用量；逐稿复核同样产生费用，必须累计而非只记最佳稿。
        result = dict(result)
        checks = [candidate["recheck"] for candidate in result.get("candidates", [])]
        for key in ("prompt_tokens", "completion_tokens", "latency_ms"):
            result[key] = result.get(key, 0) + sum(check.get(key, 0) for check in checks)
        for check in checks:
            result["cost"] = add_cost(result.get("cost"), check.get("cost"))
        self.repository.update_rewrite(audit_id, result)
        return dict(result, id=audit_id, audit_id=audit_id, disclaimer=DISCLAIMER_TEXT)

    def recheck(self, text, client_id=None):
        """同一审查路径但不写 audits；参数错误不伪装成通过。"""
        from backend.tools.db_tool import require_positive, require_text
        require_text(text, "text")
        if client_id is not None:
            require_positive(client_id, "client_id")
        self._client(client_id)
        return self.auditor.review(text, client_id=client_id)


def build_audit_tool(session, **kwargs):
    """基础设施组合入口，调用方负责 Session 的关闭。"""
    from backend.crud.audit import AuditRepository
    return AuditTool(AuditRepository(session), **kwargs)


def recheck(text, client_id):
    """MCP 的无持久化复核入口；延迟获取当前 Session 工厂。"""
    from backend.db.session import SessionLocal
    with SessionLocal() as session:
        return build_audit_tool(session).recheck(text, client_id)



class UrllibChatModel(ChatModel):
    """兼容 OpenAI 的同步聊天适配器；支持注入 transport 做离线测试。"""

    def __init__(self, transport=None):
        """读取 JUDGE_* 配置；密钥只由网络适配器保存，不进入响应。"""
        config = llm_config()
        self.model = config.get("JUDGE_MODEL", "qwen-plus")
        fallback = MODEL_PRICES.get(self.model, {})
        self.input_price = config.get('JUDGE_INPUT_PRICE_PER_M') or fallback.get('in')
        self.output_price = config.get('JUDGE_OUTPUT_PRICE_PER_M') or fallback.get('out')
        compute_cost(0, 0, self.input_price, self.output_price)
        self.pricing_source = 'configured_or_model_table' if self.input_price is not None and self.output_price is not None else 'unpriced'
        self.calls = []
        self.api_key = config.get("JUDGE_API_KEY")
        self.base_url = config.get("JUDGE_BASE_URL", DASHSCOPE_URL).rstrip("/")
        self.transport = transport if transport is not None else self._request

    def _request(self, path, payload):
        """独立聊天 HTTP 边界；错误不包含密钥、响应正文或用户文本。"""
        if not self.api_key:
            raise EmbeddingError("缺少 JUDGE_API_KEY；请在本地 .env 配置")
        request = Request(self.base_url + path, data=json.dumps(payload).encode("utf-8"),
                          headers={"Authorization": f"Bearer {self.api_key}",
                                   "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=NETWORK_TIMEOUT) as response:
                return json.load(response)
        except HTTPError as exc:
            raise EmbeddingError(f"聊天服务 HTTP {exc.code}") from None
        except (URLError, TimeoutError, ValueError, OSError):
            raise EmbeddingError("聊天服务请求失败或响应非法") from None

    def complete(self, messages: list[dict]) -> dict:
        """输入聊天消息，返回供应商真实用量和 Decimal 成本；响应缺项抛异常。"""
        started = perf_counter()
        for attempt in range(3):
            try:
                response = self.transport("/chat/completions", {
                    "model": self.model, "messages": messages, "temperature": 0,
                    "response_format": {"type": "json_object"}})
                break
            except EmbeddingError:
                if attempt == 2:
                    raise
        usage = response["usage"]
        call = dict(latency_ms=(perf_counter()-started)*1000, attempt_count=attempt+1,
                    retried=attempt>0, prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
        logging.getLogger(__name__).warning("llm_call=%s", call)
        self.calls.append(call)
        prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
        if any(type(value) is not int or value < 0 for value in (prompt, completion)):
            raise ValueError("模型用量必须是非负整数")
        content = response["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("模型内容必须是字符串")
        return {"content": content, "model": response.get("model", self.model),
                "prompt_tokens": prompt, "completion_tokens": completion,
                "cost": compute_cost(prompt, completion, self.input_price, self.output_price),
                "pricing_source": self.pricing_source}
