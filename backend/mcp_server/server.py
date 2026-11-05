"""八个独立 MCP 工具（RAG / 业务库 / 复核 / 素材解析）；stdio 服务及不访问数据的离线自检。"""

import argparse
import asyncio
import json
import os

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
            | {key: getattr(hit, key) for key in ('chunk_id', 'item_no') if hasattr(hit, key)}
            for hit in search(query, top_k=top_k)]


@mcp.tool()
def db_query_rules(axis: str | None = None) -> list[dict]:
    """读取启用规则，可按 axis 筛选；数据库异常向上传递。"""
    from backend.tools.db_tool import db_query_rules as query
    return query(axis)


@mcp.tool()
def db_query_violation_history(client_id: int, limit: int = 5, run_id: str | None = None) -> list[dict]:
    """读取机构最近违规审查；非法机构或条数报错。"""
    from backend.tools.db_tool import db_query_violation_history as query
    return query(client_id, limit, run_id)


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


@mcp.tool()
def parse_source(source_id: int, mode: str = "blank") -> dict:
    """按素材档案 id 重解析原始文件，返回逐条话术与溯源（页码/段落/置信度）。

    A1 的输入不必是"已经打在文本框里的一句话"：商家递来的是整份海报或录音，
    这个工具让智能体自己把内容取出来，而不是等人事先复制粘贴。
    """
    from backend.tools.db_tool import require_positive
    require_positive(source_id, "source_id")
    from backend.tools.ingest_tool import parse_stored
    return parse_stored(source_id, mode)


@mcp.tool()
def parse_document(rel_path: str, mode: str = "blank") -> dict:
    """解析项目 data/ 内的素材文件（示例海报、罚单附件、自检样本）。"""
    from backend.tools.ingest_tool import parse_local
    return parse_local(rel_path, mode)


async def selftest() -> None:
    """列出实际注册工具及输入签名；不调用工具、不连接数据库或模型。"""
    tools = await mcp.list_tools()
    print(json.dumps([{"name": t.name, "inputSchema": t.inputSchema} for t in tools],
                     ensure_ascii=False, indent=2))


def selftest_protocol() -> int:
    """真实经 MCP 协议（stdio 子进程 + ClientSession）调用一个工具并断言返回。

    `--selftest` 只证明"工具注册上了"，证明不了"外部客户端调得动"——
    requirements.md 那条验收线要的是后者，所以这里单独走一遍完整协议。
    选 `db_query_rules` 而不是 `rag_search_law`：它只读 MySQL，
    不碰 embedding 与模型，验收不该被网络波动绑住。
    """
    from backend.mcp_server.client import MCPError, CLIENT, call_tool

    os.environ['MCP_MODE'] = 'client'      # 这条命令本身就是协议路径，不能被"默认内联"的护栏挡住
    try:
        listed = CLIENT.tool_names()
        rows = call_tool('db_query_rules', 'absolute_terms')   # 该工具只有一个参数 axis
    except MCPError as exc:
        print(f'FAIL 协议调用失败：{exc}')
        return 1
    ok = (len(listed) == 8 and isinstance(rows, list) and rows
          and all({'axis', 'law_article', 'pattern', 'level', 'detector'} <= set(row) for row in rows))
    print(json.dumps({'transport': 'stdio', 'tools': len(listed), 'tool_names': listed,
                      'called': 'db_query_rules', 'rows': len(rows),
                      'first': {k: rows[0][k] for k in ('axis', 'level', 'detector', 'version')}
                      if rows and 'version' in rows[0] else None,
                      'assertion': 'PASS' if ok else 'FAIL'}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def warm_libraries() -> None:
    """进 stdio 协议循环前，把 jieba 的日志降噪并提前初始化一次。

    定位要写实话：我一开始怀疑"第一条协议调用超时是 jieba 把 'Building prefix dict...'
    打进 stdout、冲掉了 JSON-RPC 响应"，**这个判断被实测推翻**——隔离探针里 jieba 的
    这些输出走的是 stderr，stdout 是空的。所以这个函数只是降噪 + 把字典加载挪到握手之前，
    不要把它当成那条超时问题的修复。
    """
    import logging

    try:
        import jieba

        jieba.setLogLevel(logging.ERROR)     # 之后不再往控制台打字
        jieba.initialize()                   # 把"第一次调用才加载"挪到握手之前
    except ImportError:                       # 检索链没装 jieba 时照常跑
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--selftest-mcp", action="store_true",
                        help="起 stdio 子进程，真实经 MCP 协议调用一次工具并断言返回")
    args = parser.parse_args()
    if args.selftest_mcp:
        raise SystemExit(selftest_protocol())
    if args.selftest:
        asyncio.run(selftest())
    else:
        warm_libraries()
        mcp.run(transport="stdio")
