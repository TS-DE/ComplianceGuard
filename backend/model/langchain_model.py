"""LangChain 模型适配层：与 `UrllibChatModel` 同签名、同返回结构。

为什么要它：老师点名的技术栈里 LangChain 必须在用，而真实判定编排是显式实现的
（注册表 + 线程池 + 分级闸），不能为了"用了 LangChain"去重写判定逻辑。
所以这里**只换模型这一层**：调用方（A1/A2/A3/A4）完全不知道自己换了后端——
这正是 DIP 的验证位，换实现改的是组合根的选择，不是业务代码。

版本线要说清楚：本仓库 env 里装的是 langchain 1.x 全家桶，因此依赖
`langchain-core>=1.6.13`；适配器只用 `ChatOpenAI` 这一个入口，不碰 chain/graph API，
将来升级依赖线时受影响的只有这个文件。
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from time import perf_counter

from backend.agents.base import ChatModel
from backend.core.constants import MODEL_PRICES, compute_cost
from backend.core.errors import ModelCallError, model_error
from backend.rag.embedding import DASHSCOPE_URL, NETWORK_TIMEOUT, EmbeddingError, llm_config


class LangChainChatModel(ChatModel):
    """ChatOpenAI 打同一个 DashScope 兼容端点；客户端可注入做离线测试。"""

    def __init__(self, purpose="judge", client=None):
        """配置项与 UrllibChatModel 逐项对齐，否则两个后端会跑出两种行为。"""
        config = llm_config()
        self.backend = 'langchain'
        self.model = config.get("JUDGE_MODEL", "qwen-plus")
        fallback = MODEL_PRICES.get(self.model, {})
        self.input_price = config.get('JUDGE_INPUT_PRICE_PER_M') or fallback.get('in')
        self.output_price = config.get('JUDGE_OUTPUT_PRICE_PER_M') or fallback.get('out')
        compute_cost(0, 0, self.input_price, self.output_price)
        self.pricing_source = ('configured_or_model_table'
                               if self.input_price is not None and self.output_price is not None
                               else 'unpriced')
        self.timeout = int(config.get("JUDGE_TIMEOUT", NETWORK_TIMEOUT))
        key = "REDTEAM_ENABLE_THINKING" if purpose == "redteam" else "JUDGE_ENABLE_THINKING"
        self.thinking = (str(config[key]).lower() == "true") if key in config else None
        self.pass_thinking = str(config.get("JUDGE_PASS_THINKING_PARAM", "true")).lower() == "true"
        self.actual_thinking = self.thinking if self.pass_thinking else None
        self.api_key = config.get("JUDGE_API_KEY")
        self.base_url = config.get("JUDGE_BASE_URL", DASHSCOPE_URL).rstrip("/")
        self.calls = []
        self.deadline = None          # 与 UrllibChatModel 同义：整次请求的绝对截止时刻
        self._client = client
        # 重试交给外面那个循环：LangChain 自带的 max_retries 会把"第几次失败"藏起来，
        # 而 attempts 明细是本项目排查假死的唯一入口
        self._max_attempts = 3

    @property
    def client(self):
        """懒建客户端：默认后端是 urllib，不该因为装了 langchain 就在导入链上付代价。"""
        if self._client is None:
            from langchain_openai import ChatOpenAI   # 只在这里 import，未启用时不需要装

            if not self.api_key:
                raise EmbeddingError("缺少 JUDGE_API_KEY；请在本地 .env 配置")
            # timeout 只能给一次：既当 ChatOpenAI 字段又塞进 model_kwargs，
            # pydantic 会直接 "Found timeout supplied twice" 拒构造，表现为每次调用秒失败。
            # extra_body 也必须单传：混在 model_kwargs 里 pytest 会警告"应显式指定"，
            # 而且 langchain 1.x 之后这类混传随时会变成硬错误
            model_kwargs = {"response_format": {"type": "json_object"}}
            extra_body = ({"enable_thinking": self.actual_thinking}
                          if self.actual_thinking is not None else None)
            self._client = ChatOpenAI(model=self.model, api_key=self.api_key,
                                      base_url=self.base_url, temperature=0, max_retries=0,
                                      timeout=self.timeout, extra_body=extra_body,
                                      model_kwargs=model_kwargs)
        return self._client

    def complete(self, messages: list[dict]) -> dict:
        """返回结构与 UrllibChatModel 完全一致：content/model/tokens/cost/pricing_source。"""
        started = perf_counter()
        attempts, last_error, message = [], None, None
        for attempt in range(self._max_attempts):
            before = perf_counter()
            if self.deadline is not None and before > self.deadline:
                raise ModelCallError("模型调用超过总时间预算", "deadline_exceeded", 1)
            try:
                message = self.client.invoke(messages)
                attempts.append(dict(latency_ms=(perf_counter() - before) * 1000, error=None))
                break
            except Exception as exc:  # noqa: BLE001 - 供应商异常种类多，统一走 model_error
                error = model_error(exc, self.timeout)
                last_error = error.kind
                attempts.append(dict(latency_ms=(perf_counter() - before) * 1000,
                                     error=error.kind))
                logging.getLogger(__name__).warning('llm_attempt=%s', attempts[-1])
                if attempt + 1 >= error.attempt_limit:
                    self._record_call(started, attempts, last_error, message)
                    raise error from None
        self._record_call(started, attempts, last_error, message)
        usage = getattr(message, 'usage_metadata', None) or {}
        prompt, completion = usage.get('input_tokens'), usage.get('output_tokens')
        if any(type(value) is not int or value < 0 for value in (prompt, completion)):
            raise ValueError("模型用量必须是非负整数")
        content = message.content
        if isinstance(content, list):        # 少数端点会回分段内容，拼成字符串再交出去
            content = ''.join(part.get('text', '') if isinstance(part, dict) else str(part)
                              for part in content)
        if not isinstance(content, str):
            raise ValueError("模型内容必须是字符串")
        return {"content": content,
                "model": (message.response_metadata or {}).get('model_name', self.model),
                "prompt_tokens": prompt, "completion_tokens": completion,
                "cost": compute_cost(prompt, completion, self.input_price, self.output_price),
                "pricing_source": self.pricing_source}

    def _record_call(self, started, attempts, last_error, message):
        """成功与最终失败都留元数据；绝不记录消息内容（与 urllib 版同口径）。"""
        usage = getattr(message, 'usage_metadata', None) or {}
        reasoning = (getattr(message, 'additional_kwargs', None) or {}).get('reasoning_content') \
            or getattr(message, 'reasoning_content', '') or ''
        call = dict(thinking=self.actual_thinking, backend=self.backend,
                    latency_ms=(perf_counter() - started) * 1000, attempt_count=len(attempts),
                    retried=len(attempts) > 1, last_error=last_error, attempts=attempts,
                    prompt_tokens=usage.get('input_tokens'),
                    completion_tokens=usage.get('output_tokens'),
                    reasoning_chars=len(reasoning),
                    content_chars=len(getattr(message, 'content', '') or ''))
        logging.getLogger(__name__).warning('llm_call=%s', call)
        self.calls.append(call)
        if self.actual_thinking is False and call["reasoning_chars"]:
            raise ModelCallError("关闭思考但reasoning非空，参数未生效", "thinking_not_applied", 1)

    def dump_calls(self) -> str:
        """把调用元数据打成一行的 JSON 摘要，供压测报告引用（不含内容）。"""
        return json.dumps(self.calls, ensure_ascii=False, default=str)
