"""读超时、异常脱敏和差异化重试；全程本地mock。"""
import json
from urllib.error import HTTPError, URLError
import pytest


def model_with(monkeypatch, transport):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool,'llm_config',lambda:dict(JUDGE_TIMEOUT='180',JUDGE_API_KEY='fake-secret-123'))
    return audit_tool.UrllibChatModel(transport)


def test_timeout_message_and_two_attempts(monkeypatch):
    calls=[]
    def transport(*args):
        calls.append(1)
        raise TimeoutError('fake-secret-123')
    model=model_with(monkeypatch,transport)
    with pytest.raises(RuntimeError,match='读超时.*180') as error: model.complete([])
    assert len(calls)==2
    assert 'fake-secret' not in str(error.value)
    assert model.calls[-1]['attempt_count']==2
    assert model.calls[-1]['last_error']=='timeout'


def test_invalid_json_classified(monkeypatch):
    model=model_with(monkeypatch,lambda *args:'not JSON fake-secret-123')
    with pytest.raises(RuntimeError,match='非合法 JSON') as error: model.complete([])
    assert 'fake-secret' not in str(error.value)
    assert model.calls[-1]['attempt_count']==1


def test_http_401_not_retried(monkeypatch):
    calls=[]
    def transport(*args):
        calls.append(1)
        raise HTTPError('https://fake-secret-123',401,'body fake-secret-123',{},None)
    model=model_with(monkeypatch,transport)
    with pytest.raises(RuntimeError,match='HTTP 401') as error: model.complete([])
    assert len(calls)==1 and model.calls[-1]['attempt_count']==1
    assert 'fake-secret' not in str(error.value)


def test_connection_three_attempts_and_redaction(monkeypatch):
    calls=[]
    def transport(*args):
        calls.append(1)
        raise URLError('fake-secret-123')
    model=model_with(monkeypatch,transport)
    with pytest.raises(RuntimeError,match='连接失败') as error: model.complete([])
    assert len(calls)==3
    assert 'fake-secret' not in str(error.value)


def test_embedding_error_compatible():
    from backend.core.errors import ModelCallError
    from backend.rag.embedding import EmbeddingError
    assert issubclass(EmbeddingError,ModelCallError)


def test_reasoning_and_last_error_visible(monkeypatch):
    calls=[]
    def transport(*args):
        calls.append(1)
        if len(calls)==1: raise TimeoutError()
        return dict(choices=[dict(message=dict(content='{"hits":[]}',reasoning_content='思考内容'))],
                    usage=dict(prompt_tokens=3,completion_tokens=8))
    model=model_with(monkeypatch,transport)
    result=model.complete([])
    call=model.calls[-1]
    assert call['reasoning_chars']==4 and call['content_chars']==11
    assert call['retried'] is True and call['last_error']=='timeout'
    assert result['completion_tokens']==8
    assert len(call['attempts'])==2


def test_5xx_two_attempts(monkeypatch):
    calls=[]
    def transport(*args):
        calls.append(1)
        raise HTTPError('url',503,'secret',{},None)
    model=model_with(monkeypatch,transport)
    with pytest.raises(RuntimeError,match='HTTP 503'): model.complete([])
    assert len(calls)==2


def test_both_urlopen_use_configured_timeout(monkeypatch):
    from backend.tools import audit_tool
    from backend.rag import embedding
    seen=[]
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return b'{}'
    def opener(request,timeout):
        seen.append(timeout)
        return Response()
    config=lambda:dict(JUDGE_TIMEOUT='217',JUDGE_API_KEY='fake-secret-123')
    monkeypatch.setattr(audit_tool,'llm_config',config)
    monkeypatch.setattr(embedding,'llm_config',config)
    monkeypatch.setattr(audit_tool,'urlopen',opener)
    monkeypatch.setattr(embedding,'urlopen',opener)
    audit_tool.UrllibChatModel()._request('/chat/completions',{})
    embedding.DashScopeEmbeddingFunction()._request('/embeddings',{})
    assert seen==[217,217]
