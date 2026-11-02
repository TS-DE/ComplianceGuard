"""六个独立 MCP 工具；stdio 服务及不访问数据的离线自检。"""

import argparse
import asyncio
import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ComplianceGuard")


@mcp.tool()
def rag_search_law(query: str, top_k: int = 3) -> list[dict]:
    """按 query 检索 top_k 条法条；返回证据列表，无效输入报错。"""
    from backend.rag.retrieve import CANDIDATE_K
    from backend.tools.db_tool import require_positive, require_text
    require_text(query, "query")
    require_positive(top_k, "top_k", CANDIDATE_K)
    from backend.rag.retrieve import search
    return [{key: getattr(hit, key) for key in
             ("text", "code", "source", "score", "route", "parent_text", "doc_type")}
            for hit in search(query, top_k=top_k)]


@mcp.tool()
def db_query_rules(axis: str | None = None) -> list[dict]:
    """读取启用规则，可按 axis 筛选；数据库异常向上传递。"""
    from backend.tools.db_tool import db_query_rules as query
    return query(axis)


@mcp.tool()
def db_query_violation_history(client_id: int, limit: int = 5) -> list[dict]:
    """读取机构最近违规审查；非法机构或条数报错。"""
    from backend.tools.db_tool import db_query_violation_history as query
    return query(client_id, limit)


@mcp.tool()
def db_query_scenes() -> list[dict]:
    """读取场景及示例话术；数据库异常向上传递。"""
    from backend.tools.db_tool import db_query_scenes as query
    return query()


@mcp.tool()
def db_save_redteam_result(run_id: str, sample: str, judge: dict, category: str) -> dict:
    """追加内部红队样本；仅持久化成功返回 ok，否则报错。"""
    from backend.tools.db_tool import db_save_redteam_result as save
    return save(run_id, sample, judge, category)


@mcp.tool()
def audit_recheck(text: str, client_id: int) -> dict:
    """复用 A1 完整复核，返回真实分数、命中与本次检索法条。"""
    from backend.tools.db_tool import require_positive, require_text
    require_text(text, "text")
    require_positive(client_id, "client_id")
    from backend.tools.audit_tool import recheck
    return recheck(text, client_id)


async def selftest() -> None:
    """列出实际注册工具及输入签名；不调用工具、不连接数据库或模型。"""
    tools = await mcp.list_tools()
    print(json.dumps([{"name": t.name, "inputSchema": t.inputSchema} for t in tools],
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    if parser.parse_args().selftest:
        asyncio.run(selftest())
    else:
        mcp.run(transport="stdio")
