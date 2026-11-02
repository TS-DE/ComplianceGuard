"""行业标签及检索过滤不依赖网络，保证农业条款不混入医美依据。"""
import pytest
from backend.rag import ingest, retrieve


@pytest.fixture(autouse=True)
def clean_tables():
    yield


@pytest.mark.parametrize('text,expected', [
    ('医疗和农药', 'medical'), ('种子 水产苗种', 'agriculture'),
    ('烟草 酒类', 'tobacco_alcohol'), ('教育培训 投资回报', 'realestate_edu'),
    ('母乳 幼儿园', 'minor_media'), ('广告不得虚假', 'general'),
])
def test_domain_priority(text, expected):
    assert getattr(ingest, 'classify_domain', lambda value: None)(text) == expected


def test_children_inherit_parent_domain():
    records, _ = ingest.load_laws()
    agriculture = [r for r in records if r['metadata']['code'] in ('广告法第21条', '广告法第27条')]
    assert agriculture and all(r['metadata'].get('domain') == 'agriculture' for r in agriculture)
    assert all(r['metadata'].get('domain') for r in records)


def test_current_case_source_urls_are_preserved():
    cases = ingest.load_cases()
    assert len(cases) == 11
    assert all(r['metadata']['source'] == r['metadata']['source_url'] for r in cases)


def test_rebuild_removes_only_stale_index_ids():
    from scripts import build_index
    class Collection:
        deleted = []
        def get(self, **kwargs):
            return {'ids': ['current', 'retired']}
        def delete(self, ids):
            self.deleted.extend(ids)
    collection = Collection()
    operation = getattr(build_index, 'remove_stale', lambda c, records: None)
    operation(collection, [{'id': 'current'}])
    assert collection.deleted == ['retired']


def test_evaluation_reports_categories_and_missing_coverage():
    from scripts.evaluate_rag import evaluate
    class Engine:
        status = {}
        def search(self, query, top_k, axis=None):
            assert top_k == 3 and axis == 'safety_guarantee'
            return []
    cases = [{'id': 'x', 'query': '安全', 'expected_codes': ['广告法第16条'],
              'violation_type': 'safety_guarantee', 'source_case_id': 'samr_2025_002'}]
    result = evaluate(Engine(), cases, lexicon={
        'safety_guarantee': {'terms': [], 'queries': [], 'coverage': 'insufficient'}})
    assert result['by_type']['safety_guarantee']['coverage'] == 'insufficient'
    assert result['by_type']['safety_guarantee']['recalled'] == 0
    assert result['details'][0]['expected_codes'] == ['广告法第16条']


def test_lexicon_absent_classes_are_explicit_and_do_not_expand():
    import json
    from pathlib import Path
    lexicon = json.loads((Path(ingest.DATA_DIR) / 'lexicon/synonyms.json').read_text(encoding='utf-8'))
    for axis in ('cure_rate', 'derogatory_compare', 'inducement', 'before_after'):
        assert lexicon.get(axis) == {'terms': [], 'queries': [], 'coverage': 'no_case'}
    assert retrieve.expand_by_lexicon('治愈率 别家 容貌焦虑 术前术后对比') == []


def test_domain_filter_applies_to_bm25_and_vector_with_endorsement_exception():
    rows = [{'id': domain, 'text': '保证疗效 推荐证明', 'metadata': {
        'code': domain, 'domain': domain, 'relevance': 'decision', 'doc_type': 'law'}}
        for domain in ('agriculture', 'medical', 'realestate_edu')]
    calls = []
    class Vector:
        def query(self, name, text, k, where=None):
            calls.append(where)
            return ['agriculture', 'realestate_edu', 'medical']
    engine = retrieve.HybridRetriever(rows, [], Vector(), rewriter=lambda q: [q])
    assert [h.code for h in engine.search('保证疗效')] == ['medical']
    assert any('domain' in str(where) for where in calls)
    assert 'agriculture' in engine.status['filtered_codes']
    hits = engine.search('推荐证明', axis='endorsement')
    assert {h.code for h in hits} == {'medical', 'realestate_edu'}
