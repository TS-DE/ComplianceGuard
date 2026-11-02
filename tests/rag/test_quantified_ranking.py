"""Only quantify ranking: Article28(2), never force unseen candidates."""
import pytest
from backend.rag.retrieve import HybridRetriever


@pytest.fixture(autouse=True)
def clean_tables():
    yield


def test_quantified_query_prioritizes_existing_false_information_child(monkeypatch):
    monkeypatch.setattr('backend.rag.retrieve.expand_by_lexicon', lambda q: [])
    rows = [
        {'id': 'other', 'text': '广告法第4条\n广告不得虚假。', 'metadata': {
            'code': '广告法第4条', 'doc_type': 'law', 'domain': 'general', 'relevance': 'decision'}},
        {'id': 'false', 'text': '广告法第28条\n（二）服务内容、质量等信息与实际情况不符，对购买行为有实质性影响的；', 'metadata': {
            'code': '广告法第28条', 'doc_type': 'law', 'domain': 'general', 'relevance': 'decision'}},
    ]
    class Vector:
        def query(self, name, text, k, where=None):
            return ['other', 'false'] if name == 'law_articles' else []
    engine = HybridRetriever(rows, [], Vector(), rewriter=lambda q: [q])
    assert engine.search('拥有11家机构', top_k=3)[0].code == '广告法第28条'
    assert engine.search('数千多个家庭', top_k=3)[0].code == '广告法第28条'
    assert engine.search('普通描述', top_k=3)[0].code == '广告法第4条'
