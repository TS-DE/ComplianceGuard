"""真实 MCP 协议客户端：stdio 子进程 + ClientSession 调用本项目自己的工具。

为什么默认不走这条路（`MCP_MODE=inline`）：业务内链复用同一份实现，省掉一次进程启动
和一层序列化；把协议调用设成默认，等于为了让架构图好看而给每次审查加固定开销。
打开 client 模式只有一个用途——**证明 requirements.md 那条验收线真的能过**：
工具确实可被外部 MCP 客户端经 stdio 调用，而不是只有 `--selftest` 能列出来。

两个 Windows 上的硬要求，缺一个就必然踩坑：
1. 必须显式传当前解释器（E 盘 conda env），不能写 `python`——写 `python` 会命中 PATH
   里的 C 盘全局解释器；
2. 子进程 env 必须带 `PYTHONNOUSERSITE=1`，否则它读到 C 盘 user-site 的副本包，
   出现"父进程一套版本、子进程另一套版本"的假象，而且没有任何线索指向真正原因。

放在 `mcp_server/` 而不是 `agents/`：那是 MCP 侧的组件，且 `agents/` 已有
base/compliance/redteam 三个真实文件，再加第四个就破了"每目录 ≤3"的硬约束。
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT = 60


class MCPError(RuntimeError):
    """协议层失败。绝不静默退回内链——那会让"我在测 client 模式"变成假命题。"""


def server_params() -> StdioServerParameters:
    env = dict(os.environ)
    env['PYTHONNOUSERSITE'] = '1'                    # 子进程不许读 C 盘 user-site
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    env['PYTHONPATH'] = os.pathsep.join(
        [str(PROJECT_ROOT)] + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    return StdioServerParameters(command=env.get('MCP_PYTHON', sys.executable),
                                 args=['-X', 'utf8', '-m', 'backend.mcp_server.server'],
                                 env=env, cwd=str(PROJECT_ROOT))


def decode(result) -> object:
    """把 CallToolResult 还原成 Python 对象。

    FastMCP 对非字符串返回值会同时给 structuredContent 与 JSON 文本。优先取结构化的那份；
    只有它缺失时才解析文本——两处各解一遍，一旦上游只改其一就会出现"文本与结构不一致"的分裂结果。
    """
    structured = getattr(result, 'structuredContent', None)
    if isinstance(structured, dict) and list(structured) == ['result']:
        return structured['result']
    if structured not in (None, {}):
        return structured
    texts = [item.text for item in (getattr(result, 'content', None) or [])
             if getattr(item, 'text', None)]
    if not texts:
        raise MCPError('工具返回空内容：既没有 structuredContent，也没有文本')
    try:
        return json.loads('\n'.join(texts))
    except json.JSONDecodeError as exc:
        raise MCPError(f'工具返回不是合法 JSON：{exc.__class__.__name__}') from None


class MCPClient:
    """一个进程一条 session。

    事件循环跑在专用线程里，调用线程通过 run_coroutine_threadsafe 投递协程；
    工具调用用锁串行化——这条路是给验收用的，不追并发，追并发就该走内链。
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = int(os.environ.get('MCP_CALL_TIMEOUT', timeout))
        self.tools: list[str] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._boot_error: BaseException | None = None
        self._lock = threading.Lock()
        self._arg_order: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._session is not None:
            return
        if self._thread is None:
            self._thread = threading.Thread(target=self._serve, name='mcp-client-loop', daemon=True)
            self._thread.start()
            if not self._ready.wait(self.timeout + 10):
                raise MCPError(f'MCP 子进程在 {self.timeout + 10}s 内没有完成握手')
        if self._boot_error is not None:
            raise MCPError(f'连接 MCP server 失败：{type(self._boot_error).__name__}: '
                           f'{str(self._boot_error)[:120]}') from self._boot_error

    def _serve(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        async def boot() -> None:
            self._stack = AsyncExitStack()
            read, write = await self._stack.enter_async_context(stdio_client(server_params()))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            listed = await self._session.list_tools()
            self.tools = sorted(tool.name for tool in listed.tools)
            for tool in listed.tools:
                schema = tool.inputSchema or {}
                required = list(schema.get('required') or [])
                optional = [key for key in (schema.get('properties') or {}) if key not in required]
                self._arg_order[tool.name] = required + optional

        try:
            loop.run_until_complete(boot())        # 就在 loop 线程里跑完，不套 executor
        except BaseException as exc:  # noqa: BLE001 - 原样交给主线程判决
            self._boot_error = exc
        finally:
            self._ready.set()
        if self._boot_error is None and self._session is not None:
            loop.run_forever()                     # 之后所有请求都投递到这个 loop

    def _await(self, factory, timeout: int | None = None):
        self.start()
        with self._lock:
            future = asyncio.run_coroutine_threadsafe(factory(self._session), self._loop)
            try:
                return future.result(timeout=timeout or self.timeout)
            except TimeoutError:
                future.cancel()
                raise MCPError(f'MCP 调用超过 {timeout or self.timeout}s') from None

    def close(self) -> None:
        stack, loop = self._stack, self._loop
        self._session = None
        if stack is None or loop is None or not loop.is_running():
            return

        async def shutdown() -> None:
            await stack.aclose()

        try:
            asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout=self.timeout)
        except Exception:  # noqa: BLE001 - 退出路径上的清理失败不值得再抛一层
            pass
        finally:
            loop.call_soon_threadsafe(loop.stop)

    # ------------------------------------------------------------------ 调用
    def call(self, name: str, arguments: dict):
        if name not in self.tool_names():
            raise MCPError(f'MCP server 未注册工具 {name}')
        return decode(self._await(lambda session: session.call_tool(name, arguments)))

    def tool_names(self) -> list[str]:
        self.start()
        return self.tools


CLIENT = MCPClient()
atexit.register(CLIENT.close)


def mcp_mode() -> str:
    return str(os.environ.get('MCP_MODE', 'inline')).strip().lower()


def call_tool(name: str, /, *args, **kwargs):
    """经协议调用工具；位置参数按该工具 inputSchema 的顺序映射成关键字参数。

    刻意不做"失败自动退回内链"：静默退回会让 client 模式的验收结果不可信——
    日志上写着走过协议，实际跑的是内链，那是把验证做成了表演。
    """
    if mcp_mode() != 'client':
        raise MCPError('MCP_MODE 不是 client，不应经协议调用')
    order = CLIENT._arg_order.get(name) if CLIENT.tools else None
    if order is None:
        CLIENT.tool_names()                     # 触发 start() 并填好 _arg_order
        order = CLIENT._arg_order[name]
    arguments = dict(zip(order[:len(args)], args))
    arguments.update(kwargs)
    return CLIENT.call(name, arguments)
