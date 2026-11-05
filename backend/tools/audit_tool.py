"""审查组合根与 urllib 模型边界；数据库操作仅经仓储执行。"""
import json
from functools import lru_cache
from decimal import Decimal
from time import perf_counter
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.agents.base import ChatModel
from backend.core.config import DISCLAIMER_TEXT
from backend.core.errors import ModelCallError, model_error
from backend.core.constants import MODEL_PRICES, compute_cost, add_cost, to_refs
from backend.rag.embedding import DASHSCOPE_URL, NETWORK_TIMEOUT, EmbeddingError, llm_config

TOKENS_PER_MILLION = Decimal("1000000")
# 未指定报价时明确采用零报价，不声称这是供应商的实际收费。
DEFAULT_INPUT_PRICE = "0"
DEFAULT_OUTPUT_PRICE = "0"


@lru_cache(maxsize=256)
def _cached_law_lookup(query: str, top_k: int) -> tuple[str, ...]:
    """按 (文本, top_k) 缓存检索候选，保证同一句话在同一进程内拿到同一批法条。

    为什么必须缓存：向量检索实测有约 1/5 概率把关键法条挤出候选，
    同一句文案重复审查会因此得到不同结论。缓存把"同一输入"钉死为"同一证据集"，
    使结论可复现；跨进程仍可能变化，所以 compliance 里还有证据缺口兜底。
    用 JSON 字符串做缓存值，避免调用方就地修改命中对象污染缓存。
    """
    from backend.mcp_server.client import mcp_mode    # 只取开关，不在顶层拖上 mcp 依赖

    if mcp_mode() == 'client':
        # 走真实 MCP 协议（stdio 子进程）：requirements.md 那条"Agent 真实经 MCP 调用"
        # 只能这样验；默认仍是内联复用同一实现，因为协议模式每次要多一次进程与序列化开销
        from backend.mcp_server.client import call_tool

        items = call_tool('rag_search_law', query, top_k)
    else:
        from backend.mcp_server.server import rag_search_law

        items = rag_search_law(query, top_k)
    return tuple(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items)


def search_law(query, top_k=6):
    """复用 MCP 检索实现，延迟导入避免工具注册时循环依赖。

    top_k 取 6 而不是 3：实测同一句文案重复检索 5 次，有 1 次关键法条
    （广告法第16条 / 医美指南第5条）被挤出前 3，导致模型判出的违规因
    "法条不在候选里"被丢弃，结论翻转成合规。放宽召回 + 结果缓存降低该概率；
    真正的兜底是 compliance 里的证据缺口判定（不足即未完成，不放行）。
    """
    return [json.loads(item) for item in _cached_law_lookup(query, top_k)]


@lru_cache(maxsize=1)
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
        from backend.model import make_chat_model
        self.repository = repository
        # 后端由 LLM_BACKEND 选择（默认 urllib）：这里不再写死 UrllibChatModel，
        # 否则"换了适配层"这件事只能在组合根之外偷偷发生
        self.model = model if model is not None else make_chat_model()
        known = indexed_docs() if search_law is globals()["search_law"] else None
        self.auditor = ComplianceAuditAgent(repository.load_rules, search_law, self.model, detectors, known_docs=known,
            semantic_mode=__import__("os").environ.get("JUDGE_MODE", "merged") if known is not None else "multi")
        self.rewriter = RewriteAgent(self.auditor, self.model)

    def _client(self, client_id):
        """机构不存在报 404，None 表示不按机构限定。"""
        from backend.core.errors import NotFoundError
        if client_id is not None and not self.repository.client(client_id):
            raise NotFoundError("client", client_id)

    def _source_text(self, script):
        """取该话术所属素材的整篇文本（路线A 首 call 的上下文）。

        读库里的 `sources.full_text` 而不是重读原始文件：海报与扫描件重读要再跑一次
        OCR（实测单张 4 秒起），为了上下文而重跑识别等于用更慢换更准。
        手工录入与红队样本没有 source_id → 返回 None，判定链路自动退回
        "有语境信号才复核"的策略；这里不做任何"没上下文就当没问题"的降级。
        """
        source_id = script.get("source_id")
        if not source_id:
            return None
        from backend.db.models import Source

        row = self.repository.session.get(Source, source_id)
        return row.full_text if row else None

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
        context = self._source_text(script)
        call_offset=len(getattr(self.model,"calls",[])) if isinstance(getattr(self.model,"calls",None),list) else 0
        started = perf_counter()
        from backend.rag.embedding import usage_meter
        with usage_meter() as rag_usage:
            result = self.auditor.review(script["content"], client_id=client_id, context=context)
        result["cost_breakdown"] = dict(a1=dict(cost=result["cost"],prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"]), **rag_usage)
        result["cost"] = add_cost(add_cost(result["cost"],rag_usage["rag_rewrite"]["cost"]),rag_usage["embedding"]["cost"])
        result["cost_label"] = "全链路估算，非供应商账单"
        result.update(judge_cost=result["cost_breakdown"]["a1"]["cost"],
                      rewrite_cost=rag_usage["rag_rewrite"]["cost"],embedding_cost=rag_usage["embedding"]["cost"],
                      total_cost=result["cost"],cost_note=("全链路估算，非供应商账单；仅 embedding 已计价，其他未知项不计伪合计"
                          if result["cost"] is None and rag_usage["embedding"]["cost"] is not None
                          else "全链路估算，非供应商账单；未知项不计伪合计"))
        result["llm_calls"] = getattr(self.model,"calls",[])[call_offset:]
        before = perf_counter()
        audit_id = self.repository.save(script_id, result)
        result.setdefault("timings_ms", {})["persist"] = (perf_counter() - before) * 1000
        result["latency_ms"] = int((perf_counter() - started) * 1000)
        if hasattr(self.repository, "update_latency"):
            self.repository.update_latency(audit_id, result["latency_ms"])
        logging.getLogger(__name__).warning("audit_timings_ms=%s", result["timings_ms"])
        result["llm_calls"] = getattr(self.model, "calls", [])[call_offset:]
        return dict(result, id=audit_id, audit_id=audit_id, script_id=script_id)

    def rewrite_audit(self, audit_id, budget_seconds=None):
        """以原话术与有效命中生成改写，复核后持久化状态。

        `budget_seconds` 是**整次请求**的时间预算：单次读超时（JUDGE_TIMEOUT=180）
        拦不住"重试 3 次 × 每个候选各判一遍"的累加，实测就是这样出现过 10 分钟假死。
        预算用尽时抛 DeadlineExceededError；此时还没走到 update_rewrite，
        库里与响应里都不会出现半成品改写稿。
        """
        from backend.core.errors import DeadlineExceededError, ModelCallError, NotFoundError
        from backend.tools.db_tool import require_positive
        require_positive(audit_id, "audit_id")
        audit = self.repository.audit(audit_id)
        if audit is None:
            raise NotFoundError("audit", audit_id)
        script = self.repository.script(audit["script_id"])
        hits = [hit for hit in audit["hits"] if hit.get("status", "active") == "active"]
        deadline = perf_counter() + budget_seconds if budget_seconds else None
        # 预算要发给**所有真的会打模型的持有者**：tool / rewriter / auditor。
        # 当下生产上它们是同一个实例，只设 self.model 也能过——但那是在赌对象身份；
        # 一旦有人单独注入模型实例，90 秒上限就会悄悄失效且没有任何报错。
        holders = []
        for candidate in (self.model, getattr(self.rewriter, 'model', None),
                          getattr(self.auditor, 'model', None)):
            if candidate is not None and hasattr(candidate, 'deadline') \
                    and not any(candidate is held for held in holders):
                holders.append(candidate)
        try:
            for holder in holders:
                holder.deadline = deadline
            result = self.rewriter.rewrite(script["content"], hits, client_id=script["client_id"])
        except ModelCallError as exc:
            if exc.kind == 'deadline_exceeded':
                raise DeadlineExceededError(int(budget_seconds or 0)) from None
            raise
        finally:
            for holder in holders:
                holder.deadline = None      # 预算属于这一次请求，不许漏给下一个请求
        # A2 返回的是生成用量；逐稿复核同样产生费用，必须累计而非只记最佳稿。
        result = dict(result)
        checks = [candidate["recheck"] for candidate in result.get("candidates", [])]
        for key in ("prompt_tokens", "completion_tokens", "latency_ms"):
            result[key] = result.get(key, 0) + sum(check.get(key, 0) for check in checks)
        for check in checks:
            result["cost"] = add_cost(result.get("cost"), check.get("cost"))
        self.repository.update_rewrite(audit_id, result)
        return dict(result, id=audit_id, audit_id=audit_id, disclaimer=DISCLAIMER_TEXT)

    def review_source(self, source_id: int, client_id: int | None = None,
                      limit: int = 20) -> dict:
        """A1 的第二个入口：直接吃一份上传素材（海报/扫描件/录音），当场审、不落库。

        为什么要单独一条路："先入库再审查"意味着商家只想试一下的素材也被迫写进
        业务表，之后的审计统计全被这批没留档决心的数据污染。
        预审只给结论与溯源，`persisted=false` 明说库里没有记录。

        上限 20 条与 /audit/batch 同口径：单条约 6 秒，再多浏览器会超时。
        逐条独立 try —— 一条模型故障只标该条"未完成"，不许把整批算成合规。
        """
        from backend.core.errors import BusinessValidationError
        from backend.tools.db_tool import require_positive
        from backend.tools.ingest_tool import parse_stored, source_owner

        require_positive(source_id, "source_id")
        if client_id is not None:
            require_positive(client_id, "client_id")
            self._client(client_id)
        owner = source_owner(source_id)
        if client_id is not None and owner["client_id"] != client_id:
            raise BusinessValidationError("素材不属于指定机构")
        parsed = parse_stored(source_id)
        all_items = parsed["items_detail"]
        if not all_items:
            raise BusinessValidationError("该素材切不出可审查的话术条目（可能全是 4 字以下噪声）")
        items = all_items[:limit]

        results = []
        for item in items:
            entry = {"text": item["text"], "ref": item["ref"],
                     "confidence": item["confidence"]}
            try:
                verdict = self.auditor.review(item["text"], client_id=owner["client_id"])
                entry.update(score=verdict["score"], incomplete=bool(verdict.get("incomplete")),
                             hit_count=len(verdict.get("hits") or []),
                             hits=verdict.get("hits") or [])
            except Exception as exc:  # 单条故障不外泄堆栈，但要留下可见的未完成标记
                logging.getLogger(__name__).warning("preview_source_failed id=%s err=%s",
                                                   source_id, type(exc).__name__)
                entry.update(score=-1, incomplete=True, hit_count=0, hits=[],
                             error=f"判定未完成（{type(exc).__name__}），需人工复核")
            results.append(entry)
        return {"source_id": source_id, "filename": owner["filename"],
                "kind": owner["kind"], "engine": owner["engine"],
                "count": len(results), "total_items": len(all_items),
                # 截断必须显式说：否则"审了 20 条"在页面上看起来像"整份都审完了"
                "truncated": len(all_items) > len(items),
                "warnings": parsed.get("warnings") or [],
                "persisted": False, "results": results,
                "disclaimer": DISCLAIMER_TEXT}

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

    def __init__(self, transport=None, purpose="judge"):
        """读取 JUDGE_* 配置；密钥只由网络适配器保存，不进入响应。"""
        config = llm_config()
        self.model = config.get("JUDGE_MODEL", "qwen-plus")
        fallback = MODEL_PRICES.get(self.model, {})
        self.input_price = config.get('JUDGE_INPUT_PRICE_PER_M') or fallback.get('in')
        self.output_price = config.get('JUDGE_OUTPUT_PRICE_PER_M') or fallback.get('out')
        compute_cost(0, 0, self.input_price, self.output_price)
        self.pricing_source = 'configured_or_model_table' if self.input_price is not None and self.output_price is not None else 'unpriced'
        self.timeout = int(config.get("JUDGE_TIMEOUT", NETWORK_TIMEOUT))
        key = "REDTEAM_ENABLE_THINKING" if purpose == "redteam" else "JUDGE_ENABLE_THINKING"
        self.thinking = (str(config[key]).lower() == "true") if key in config else None
        self.pass_thinking = str(config.get("JUDGE_PASS_THINKING_PARAM", "true")).lower() == "true"
        self.actual_thinking = self.thinking if self.pass_thinking else None
        self.calls = []
        # 总时间预算（perf_counter 的绝对时刻）：单次读超时不等于总耗时上限，
        # 3 次重试 × 180s 就是 9 分钟假死——改写接口用它把整次请求封顶。
        self.deadline = None
        self.attempt_timeout = self.timeout   # 每次尝试真正用的读超时（预算紧时会被压小）
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
        # urllib timeout作用于单次阻塞读操作，不是请求总耗时截止时间——所以总预算必须由
        # 调用方把剩余时间写进 self.attempt_timeout；否则"90 秒硬超时"在"单次调用很久"
        # 这种情况下根本不成立（最坏会到 90 + 180 秒）。
        with urlopen(request, timeout=self.attempt_timeout) as response:
            return json.load(response)

    def complete(self, messages: list[dict]) -> dict:
        """输入聊天消息，返回供应商真实用量和 Decimal 成本；响应缺项抛异常。"""
        started = perf_counter()
        attempts=[]
        last_error=None
        for attempt in range(3):
            before=perf_counter()
            if self.deadline is not None:
                remaining = self.deadline - before
                if remaining <= 0:
                    # 预算用尽就立刻收手：继续重试只是把"9 分钟假死"再演一遍
                    raise ModelCallError("模型调用超过总时间预算", "deadline_exceeded", 1)
                # 剩余预算压进单次读超时，硬上限才对"单次很慢"这种情况成立
                self.attempt_timeout = max(1, min(self.timeout, int(remaining) or 1))
            else:
                self.attempt_timeout = self.timeout
            try:
                payload=dict(model=self.model,messages=messages,temperature=0,response_format={'type':'json_object'})
                if self.actual_thinking is not None:
                    payload['enable_thinking']=self.actual_thinking
                response = self.transport('/chat/completions', payload)
                if not isinstance(response,dict):
                    response=json.loads(response)
                attempts.append(dict(latency_ms=(perf_counter()-before)*1000,error=None))
                break
            except (ModelCallError, HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
                error=model_error(exc,self.timeout)
                last_error=error.kind
                attempts.append(dict(latency_ms=(perf_counter()-before)*1000,error=error.kind))
                logging.getLogger(__name__).warning('llm_attempt=%s',attempts[-1])
                if attempt+1>=error.attempt_limit:
                    self._record_call(started,attempts,last_error,None)
                    raise error from None
        self._record_call(started,attempts,last_error,response)
        usage = response['usage']
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


    def _record_call(self, started, attempts, last_error, response):
        """成功和最终失败均记录元数据，绝不记录消息内容。"""
        usage=(response or {}).get('usage',{})
        choices=(response or {}).get('choices') or [{}]
        message=choices[0].get('message',{})
        call=dict(thinking=self.actual_thinking,latency_ms=(perf_counter()-started)*1000,attempt_count=len(attempts),
                  retried=len(attempts)>1,last_error=last_error,attempts=attempts,
                  prompt_tokens=usage.get('prompt_tokens'),completion_tokens=usage.get('completion_tokens'),
                  reasoning_chars=len(message.get('reasoning_content') or ''),content_chars=len(message.get('content') or ''))
        logging.getLogger(__name__).warning('llm_call=%s',call)
        self.calls.append(call)
        if self.actual_thinking is False and call["reasoning_chars"]:
            raise ModelCallError("关闭思考但reasoning非空，参数未生效", "thinking_not_applied", 1)
