"""MCP 协议客户端的离线测试：不起子进程，只测客户端自身的逻辑与守卫。

真跑协议那条路由 `python -m backend.mcp_server.server --selftest-mcp` 与验收脚本负责，
写进 pytest 会让全套测试依赖子进程与 Chroma 冷启动（实测首 call 约 90 秒），
那是把"能不能测"绑在环境上。这里锁的是**换协议不能改变语义**的那些部分。
"""

import json
import sys

import pytest

from backend.mcp_server import client as mcp_client
from backend.mcp_server.client import MCPClient, MCPError, decode, server_params


class Result:
    def __init__(self, structured=None, texts=()):
        self.structuredContent = structured
        self.content = [type('C', (), {'text': t})() for t in texts]


def test_decode_prefers_structured_result():
    assert decode(Result(structured={'result': [{'a': 1}]})) == [{'a': 1}]


def test_decode_passes_through_other_structured_shapes():
    assert decode(Result(structured={'ok': True})) == {'ok': True}


def test_decode_falls_back_to_text_json():
    assert decode(Result(texts=[json.dumps([{'code': '广告法第16条'}])])) == [{'code': '广告法第16条'}]


def test_decode_rejects_garbage_and_empty():
    with pytest.raises(MCPError, match='空内容'):
        decode(Result())
    with pytest.raises(MCPError, match='不是合法 JSON'):
        decode(Result(texts=['这不是 JSON']))


def test_server_params_pins_interpreter_and_user_site(monkeypatch):
    """Windows 上两个必须钉住的点：解释器路径与 PYTHONNOUSERSITE，否则子进程会读到 C 盘副本包。"""
    monkeypatch.delenv('MCP_PYTHON', raising=False)
    params = server_params()
    assert params.command == sys.executable
    assert params.args == ['-X', 'utf8', '-m', 'backend.mcp_server.server']
    assert params.env['PYTHONNOUSERSITE'] == '1'
    assert str(mcp_client.PROJECT_ROOT) in params.env['PYTHONPATH']
    assert params.cwd == str(mcp_client.PROJECT_ROOT)


def test_server_params_honours_explicit_python(monkeypatch):
    monkeypatch.setenv('MCP_PYTHON', r'D:\elsewhere\python.exe')
    assert server_params().command == r'D:\elsewhere\python.exe'


def test_construction_does_not_spawn_subprocess():
    """构造客户端不许有副作用：导入路径上被调到就会拖慢整个测试套件。"""
    client = MCPClient()
    assert client._thread is None and client._session is None


def test_inline_mode_refuses_protocol_call(monkeypatch):
    monkeypatch.setenv('MCP_MODE', 'inline')
    with pytest.raises(MCPError, match='MCP_MODE 不是 client'):
        mcp_client.call_tool('db_query_rules', 'absolute_terms')


def test_positional_args_map_by_input_schema_order(monkeypatch):
    """位置参数按工具的 inputSchema 顺序映射；映射错了就是"传了参数但等于没传"。"""
    monkeypatch.setenv('MCP_MODE', 'client')          # 先过开关守卫，才轮到参数映射
    client = MCPClient()
    client.tools = ['db_query_violation_history']
    client._arg_order = {'db_query_violation_history':
                         ['client_id', 'limit', 'run_id']}
    seen = {}
    client.call = lambda name, arguments: seen.update(name=name, **arguments) or 'ok'
    monkeypatch.setattr(mcp_client, 'CLIENT', client)
    assert mcp_client.call_tool('db_query_violation_history', 7, 3) == 'ok'
    assert seen == {'name': 'db_query_violation_history', 'client_id': 7, 'limit': 3}


def test_unknown_tool_is_refused_before_the_wire(monkeypatch):
    """未注册的工具名不许发到底层：`tool_names()` 会启动子进程，测试里必须打桩。"""
    client = MCPClient()
    client.tools = ['rag_search_law']
    client._arg_order = {'rag_search_law': ['query', 'top_k']}
    client.tool_names = lambda: client.tools
    with pytest.raises(MCPError, match='未注册工具'):
        client.call('delete_everything', {})


PROBE_CLEAN = """
import sys
from backend.mcp_server.server import warm_libraries

warm_libraries()                      # 协议通道接管前的预热与静音
import jieba
jieba.lcut("保证三个月恢复正常肤色")     # 之后真正用一次分词
sys.stderr.write("PROBE_DONE")
"""
PROBE_DIRTY = """
import jieba
print("Building prefix dict from the default dictionary ...")   # 模拟往 stdout 打字
"""


def test_child_stdout_stays_empty_for_the_protocol_channel(tmp_path):
    """stdio 子进程的 stdout 是 JSON-RPC 专用通道，业务路径不许往里写东西。

    先说清这条测试的来历，不给自己脸上贴金：我最初判断"第一条协议调用超时是 jieba
    把 'Building prefix dict...' 打到 stdout 冲掉了响应"，**这个判断是错的**——
    隔离实测 jieba 的这些输出走的是 stderr，且 stdout 干净。真正的超时原因见 CHANGELOG。
    所以这条是**护栏**（将来任何库把 print 打到 stdout 都会被它抓住），不是某个已修 bug 的回归。

    为了让它可判真伪，先跑一个"故意打印"的对照组：捕获机制必须能抓到污染，
    否则第二条断言就是空跑。
    """
    import os
    import subprocess
    import sys

    env = {**os.environ, 'PYTHONNOUSERSITE': '1',
           'PYTHONPATH': os.pathsep.join([str(mcp_client.PROJECT_ROOT),
                                          os.environ.get('PYTHONPATH', '')]).rstrip(os.pathsep)}

    dirty = tmp_path / 'dirty.py'
    dirty.write_text(PROBE_DIRTY, encoding='utf-8')
    caught = subprocess.run([sys.executable, '-X', 'utf8', str(dirty)],
                            capture_output=True, text=True, timeout=300, env=env)
    assert 'Building prefix dict' in caught.stdout, '对照组没抓到污染，说明捕获失效'

    clean = tmp_path / 'clean.py'
    clean.write_text(PROBE_CLEAN, encoding='utf-8')
    result = subprocess.run([sys.executable, '-X', 'utf8', str(clean)],
                            capture_output=True, text=True, timeout=300, env=env)
    assert result.returncode == 0, result.stderr[-400:]
    assert 'PROBE_DONE' in result.stderr
    assert result.stdout == '', f'预热或分词往 stdout 写了东西：{result.stdout[:200]!r}'
