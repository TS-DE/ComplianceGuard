"""混合检索的秩融合与故障降级测试。"""
import importlib


def module():
    try:
        return importlib.import_module('backend.rag.retrieve')
    except ModuleNotFoundError:
        assert False, 'retrieve 尚未实现'


def test_lexicon_expands_and_survives_network_failure():
    m = module()
    assert any('功效' in q for q in m.expand_by_lexicon('保证白一个色度'))
    record = {'id': 'a', 'text': '医疗广告不得对功效作断言或者保证',
              'metadata': {'code': '广告法第16条', 'parent_text': '全文',
                           'doc_type': 'law', 'relevance': 'decision'}}
    def broken(q):
        raise RuntimeError('LLM offline')
    retriever = m.HybridRetriever([record], [], None, rewriter=broken)
    hits = retriever.search('保证白一个色度')
    assert hits and 'lexicon' in hits[0].route and 'degraded' in hits[0].route


def test_rrf_uses_ranks():
    m = module()
    scores = m.rrf_fuse([['a', 'b'], ['b', 'c']])
    assert scores['b'] > scores['a']
    assert abs(scores['b'] - (1 / 62 + 1 / 61)) < 1e-10


def test_vector_failure_keeps_bm25():
    m = module()
    record = {'id': 'law1', 'text': '医疗广告不得保证疗效',
              'metadata': {'code': '广告法第16条', 'parent_text': '医疗广告不得保证疗效',
                           'doc_type': 'law', 'relevance': 'decision', 'source': 'test'}}

    class Unavailable:
        def query(self, *args, **kwargs):
            raise RuntimeError('offline')

    retriever = m.HybridRetriever([record], [], Unavailable(), rewriter=lambda q: [q])
    hits = retriever.search('医疗广告保证疗效')
    assert hits and hits[0].code == '广告法第16条'
    assert 'degraded' in hits[0].route
    assert retriever.status['degraded'] == 'vector_unavailable'
