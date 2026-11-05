"""模型后端的选择点：`LLM_BACKEND=urllib|langchain`，默认 urllib。

编排（注册表路由、线程池、分级闸、三重校验）是显式实现，不在这一层；
这一层只回答一个问题：这次请求的 chat 调用交给哪个实现。

默认留在 urllib 是有理由的：它是已实测跑通 381 条测试与全部红队/锚点验证的那条路，
LangChain 作为可切换后端先并轨验证，不做默认——切换要能一键回退，才算"每次提交可回滚"。
"""

from __future__ import annotations

from backend.agents.base import ChatModel
from backend.model.langchain_model import LangChainChatModel
from backend.rag.embedding import llm_config

__all__ = ['ChatModel', 'LangChainChatModel', 'make_chat_model']


def make_chat_model(purpose: str = "judge", transport=None, client=None) -> ChatModel:
    """按配置返回一个 ChatModel；调用方不感知具体后端。

    `transport` 只对 urllib 有效（离线测试注入 HTTP），`client` 只对 langchain 有效；
    传了对应注入项就当调用方显式要求该后端，不再看环境变量——否则测试里换 mock、
    线上开关又是另一个后端，测的就不是跑的那条路。
    """
    backend = str(llm_config().get("LLM_BACKEND", "urllib")).strip().lower()
    if backend == "langchain" or client is not None:
        return LangChainChatModel(purpose=purpose, client=client)
    if backend not in ("urllib", ""):
        raise ValueError(f"LLM_BACKEND 只支持 urllib / langchain，当前是 {backend!r}")
    from backend.tools.audit_tool import UrllibChatModel   # 延迟导入：避开 tools→model→tools 的环

    return UrllibChatModel(transport=transport, purpose=purpose)
