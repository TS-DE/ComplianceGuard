"""Embedding 接口与自动分批行为。"""
import importlib


def test_batches_are_limited_to_25():
    try:
        module = importlib.import_module('backend.rag.embedding')
    except ModuleNotFoundError:
        assert False, 'embedding 模块尚未实现'
    calls = []

    def transport(path, payload):
        calls.append(len(payload['input']))
        return {'data': [{'index': i, 'embedding': [0.1] * 1024}
                         for i, _ in enumerate(payload['input'])]}

    embedding = module.DashScopeEmbeddingFunction(api_key='test', transport=transport)
    assert len(embedding(['条文'] * 51)) == 51
    assert calls == [25, 25, 1]


def test_malformed_vectors_raise_explicit_error():
    import pytest
    from backend.rag.embedding import DashScopeEmbeddingFunction, EmbeddingError
    embedding = DashScopeEmbeddingFunction(api_key='test', transport=lambda *_: {'data': []})
    with pytest.raises(EmbeddingError, match='向量数量'):
        embedding(['原文'])


def test_no_key_never_returns_empty_vectors():
    import pytest
    from backend.rag.embedding import DashScopeEmbeddingFunction, EmbeddingError
    embedding = DashScopeEmbeddingFunction(api_key='test')
    embedding.api_key = None
    with pytest.raises(EmbeddingError, match='JUDGE_API_KEY'):
        embedding(['原文'])
