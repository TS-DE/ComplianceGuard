"""两个模型后端的等价性契约（T-B 验收的可测部分）。

`LLM_BACKEND=urllib|langchain` 只换"这次 chat 调用交给谁"，判定编排一个字都没改。
所以这里测的不是"langchain 能不能跑"，而是**两后端在同一次请求上给出的东西是否同构**：
返回字段、成本口径、重试语义、错误分类。任何一项对不上，切换后端就会悄悄改变判定结果。
"""

import json
from types import SimpleNamespace

import pytest

from backend.core.errors import ModelCallError, model_error
from backend.model import LangChainChatModel, make_chat_model
from backend.tools.audit_tool import UrllibChatModel

CANNED = {'choices': [{'message': {'content': '{"efficacy_claim":[]}'}}],
          'model': 'qwen-plus', 'usage': {'prompt_tokens': 120, 'completion_tokens': 30}}


def langchain_message():
    """伪造一个 AIMessage 形状（content + usage_metadata + response_metadata）。"""
    return SimpleNamespace(content='{"efficacy_claim":[]}',
                           usage_metadata={'input_tokens': 120, 'output_tokens': 30,
                                           'total_tokens': 150},
                           response_metadata={'model_name': 'qwen-plus'},
                           additional_kwargs={})


class FakeClient:
    def __init__(self, message=None, raises=None):
        self.message, self.raises, self.seen = message or langchain_message(), raises, []

    def invoke(self, messages):
        self.seen.append(messages)
        if self.raises:
            raise self.raises
        return self.message


def test_real_client_construction_is_valid(monkeypatch):
    """真构造一次 ChatOpenAI（不联网）：字段冲突在构造期就炸，注入假客户端测不到。

    这条就是 `timeout` 同时出现在 ChatOpenAI 字段和 model_kwargs 里那个 bug 的回归测试——
    当时 pydantic 报 "Found timeout supplied twice"，表现为每次调用 7ms 秒失败、
    score 全变 -1，而注入 fake client 的 10 条测试全绿。
    """
    monkeypatch.setenv('JUDGE_API_KEY', 'sk-not-a-real-key')
    monkeypatch.setenv('JUDGE_BASE_URL', 'https://example.invalid/compatible-mode/v1')
    model = LangChainChatModel()
    client = model.client
    assert client.__class__.__name__ == 'ChatOpenAI'
    # 真实字段名是 request_timeout（`timeout=` 只是别名），探针查过：没有 .timeout 这个属性
    assert float(client.request_timeout) == float(model.timeout)
    assert client.model_kwargs.get('response_format') == {'type': 'json_object'}, client.model_kwargs
    assert 'timeout' not in client.model_kwargs and 'extra_body' not in client.model_kwargs


def test_client_without_key_fails_loud(monkeypatch):
    # 必须打在适配器模块的名字上：那里是 `from ... import llm_config`，改源模块不影响它
    monkeypatch.setattr('backend.model.langchain_model.llm_config',
                        lambda: {'JUDGE_BASE_URL': 'https://example.invalid/v1'})
    with pytest.raises(Exception, match='JUDGE_API_KEY'):
        LangChainChatModel().client


def test_default_backend_stays_urllib(monkeypatch):
    """默认必须是已实测跑通全部测试的那条路，切换要显式。"""
    monkeypatch.delenv('LLM_BACKEND', raising=False)
    assert type(make_chat_model()) is UrllibChatModel
    monkeypatch.setenv('LLM_BACKEND', 'langchain')
    assert type(make_chat_model()) is LangChainChatModel


def test_unknown_backend_fails_loud(monkeypatch):
    """写错开关不能悄悄退回默认值：那会让"我在测 langchain"变成"其实在测 urllib"。"""
    monkeypatch.setenv('LLM_BACKEND', 'litellm')
    with pytest.raises(ValueError, match='LLM_BACKEND'):
        make_chat_model()


def test_both_backends_return_the_same_shape():
    """同一份响应，两个后端必须给出逐字段相同的返回体。"""
    urllib_model = UrllibChatModel(transport=lambda path, payload: CANNED)
    lc_model = LangChainChatModel(client=FakeClient())
    left = urllib_model.complete([{'role': 'user', 'content': 'x'}])
    right = lc_model.complete([{'role': 'user', 'content': 'x'}])
    assert set(left) == set(right)
    for key in ('content', 'model', 'prompt_tokens', 'completion_tokens', 'pricing_source'):
        assert left[key] == right[key], key
    assert str(left['cost']) == str(right['cost']), (left['cost'], right['cost'])


def test_langchain_receives_the_same_payload_as_the_openai_wire():
    """messages 原样交给 ChatOpenAI，不重新拼 prompt：编排层是同一份，才能对比。"""
    client = FakeClient()
    LangChainChatModel(client=client).complete([{'role': 'system', 'content': 'S'},
                                                {'role': 'user', 'content': 'U'}])
    assert client.seen[0] == [{'role': 'system', 'content': 'S'}, {'role': 'user', 'content': 'U'}]


def test_missing_usage_is_refused_not_guessed():
    """供应商没回用量时不能记 0：0 会被当成"这次很便宜"，是假数字。"""
    message = SimpleNamespace(content='{}', usage_metadata=None,
                              response_metadata={}, additional_kwargs={})
    with pytest.raises(ValueError, match='非负整数'):
        LangChainChatModel(client=FakeClient(message=message)).complete([])


def test_segmented_content_is_flattened():
    """部分端点把内容切成多段返回，交出去之前必须是拼接后的字符串。"""
    message = SimpleNamespace(content=[{'type': 'text', 'text': '{"a":'}, {'type': 'text', 'text': '[]}'}],
                              usage_metadata={'input_tokens': 1, 'output_tokens': 1},
                              response_metadata={}, additional_kwargs={})
    assert LangChainChatModel(client=FakeClient(message=message)).complete([])['content'] == '{"a":[]}'


def test_http_status_from_sdk_keeps_urllib_retry_semantics():
    """4xx 不重试、5xx 重试两次——这条语义在 urllib 路径上已经存在，langchain 必须一致。"""
    for status, limit in ((400, 1), (429, 1), (503, 2)):
        error = model_error(SimpleNamespace(status_code=status, args=('x',), body=None), 180)
        assert error.kind == 'http' and error.attempt_limit == limit, status


def test_timeout_error_class_from_sdk_maps_to_timeout():
    class APITimeoutError(Exception):
        pass

    error = model_error(APITimeoutError(), 180)
    assert error.kind == 'timeout' and error.attempt_limit == 2


def test_langchain_error_is_retried_then_raised_without_content():
    """失败要重试到上限再抛，且抛出的错误里不能有密钥或用户文本。"""
    client = FakeClient(raises=RuntimeError('boom'))
    model = LangChainChatModel(client=client)
    with pytest.raises(ModelCallError):
        model.complete([{'role': 'user', 'content': '保证三个月恢复正常肤色'}])
    assert len(client.seen) == 3, "未知网络错误按 3 次尝试，与 urllib 路径同口径"
    assert model.calls[-1]['retried'] is True
    assert model.calls[-1]['backend'] == 'langchain'
    assert 'boom' not in json.dumps(model.calls[-1], default=str, ensure_ascii=False)


def test_error_message_never_leaks_key_or_prompt():
    model = LangChainChatModel(client=FakeClient(raises=ValueError('bad json')))
    with pytest.raises(ModelCallError) as exc:
        model.complete([{'role': 'user', 'content': 'SECRET-PROMPT'}])
    assert 'SECRET-PROMPT' not in str(exc.value)
    assert exc.value.kind == 'invalid_json'
