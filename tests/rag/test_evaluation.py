"""Evaluator contract: official metrics always use three results."""
from types import SimpleNamespace
import pytest
from scripts.evaluate_rag import evaluate


@pytest.fixture(autouse=True)
def clean_tables():
    """Pure diagnostic tests do not require the SQL integration database."""
    yield


class StubRetriever:
    def __init__(self, codes):
        self.codes = codes
        self.status = {}
        self.calls = []

    def search(self, query, top_k=3, axis=None):
        self.calls.append(top_k)
        return [SimpleNamespace(code=c, score=0.1, route='bm25') for c in self.codes[:top_k]]


def case(expected=('expected',), acceptable=('acceptable',), kind='absolute_terms'):
    return dict(id='one', query='query', expected_codes=list(expected),
                acceptable_codes=list(acceptable), violation_type=kind, source_case_id='source')


def test_strict_relaxed_partial_and_article_precision():
    retriever = StubRetriever(['acceptable', 'other'])
    result = evaluate(retriever, [case()])
    assert result['strict_hits'] == 0
    assert result['relaxed_hits'] == 1
    assert result['partial_hits'] == 1
    assert result['article_accuracy'] == 0
    assert result['relaxed_article_precision'] == 0.5
    assert result['top1_accuracy'] == 0
    assert result['by_type']['absolute_terms']['partial_hits'] == 1
    assert retriever.calls == [3]


class Collection:
    def __init__(self, metadata):
        self.metadata = metadata
        self.calls = []

    def get(self, where):
        self.calls.append(where)
        rows = self.metadata.get(where['code'], [])
        return dict(ids=[str(i) for i in range(len(rows))], metadatas=rows)


def diagnosed(codes, metadata, *, acceptable=('acceptable',), coverage='ok', top50=()):
    from scripts.rag_diagnose import diagnose_failures
    retriever = StubRetriever(codes)
    collection = Collection(metadata)
    retriever.vector = SimpleNamespace(client=SimpleNamespace(
        get_collection=lambda name: collection))
    result = evaluate(retriever, [case(acceptable=acceptable)])
    rows = diagnose_failures(retriever, result, lexicon={
        'absolute_terms': {'coverage': coverage}},
        top50_search=lambda row: list(top50))
    return rows, collection


@pytest.mark.parametrize('codes,metadata,coverage,top50,want', [
    (['acceptable'], {}, 'ok', (), 'A'),
    (['other'], {}, 'ok', (), 'B'),
    (['other'], {'expected': [{'domain': 'realestate_edu', 'relevance': 'decision'}]}, 'ok', (), 'C'),
    (['other'], {'expected': [{'domain': 'medical', 'relevance': 'navigation'}]}, 'ok', (), 'C'),
    (['other'], {'expected': [{'domain': 'medical', 'relevance': 'decision'}]}, 'ok', ('expected',), 'D'),
    (['other'], {'expected': [{'domain': 'medical', 'relevance': 'decision'}]}, 'no_case', (), 'E'),
    (['other'], {'expected': [{'domain': 'medical', 'relevance': 'decision'}]}, 'ok', (), 'unclassified'),
])
def test_diagnoses_evidence_and_explicit_gap(codes, metadata, coverage, top50, want):
    rows, collection = diagnosed(codes, metadata, coverage=coverage, top50=top50)
    assert rows[0]['category'] == want
    assert rows[0]['query'] == 'query'
    assert rows[0]['expected_codes'] == ['expected']
    assert rows[0]['actual_codes'] == codes
    assert rows[0]['reason'] and rows[0]['remedy']
    if want != 'A':
        assert collection.calls == [{'code': 'expected'}]
    if want == 'C':
        assert 'expected' in rows[0]['filtered_codes']


def test_acceptable_annotation_without_actual_hit_is_not_a():
    rows, _ = diagnosed(['other'], {})
    assert rows[0]['category'] == 'B'


def test_collection_unavailable_is_not_evidence_of_absence():
    from scripts.rag_diagnose import diagnose_failures
    retriever = StubRetriever(['other'])
    result = evaluate(retriever, [case()])
    rows = diagnose_failures(retriever, result,
        lexicon={'absolute_terms': {'coverage': 'ok'}}, top50_search=lambda row: [])
    assert rows[0]['category'] == 'unclassified'
    assert rows[0]['collection_inspection'] == 'unavailable'


def test_experimental_controls_restore_globals_and_disable_network(monkeypatch):
    from backend.rag import retrieve
    from scripts.rag_diagnose import ControlledRetriever
    seen = []
    class Probe(StubRetriever):
        rewriter = staticmethod(lambda text: (_ for _ in ()).throw(AssertionError('network')))
        def search_vector(self, *args):
            raise AssertionError('network')
        def search(self, query, top_k=3, axis=None):
            seen.append((retrieve.CANDIDATE_K, retrieve.rrf_fuse([['x']])['x'],
                         self.rewriter(query), retrieve.expand_by_lexicon(query)))
            with pytest.raises(Exception, match='offline'):
                self.search_vector(query, 3)
            return super().search(query, top_k, axis)
    original_k, original_fuse = retrieve.CANDIDATE_K, retrieve.rrf_fuse
    controlled = ControlledRetriever(Probe(['expected']), rrf_k=10, rewrite=False, lexicon=False, offline=True)
    assert evaluate(controlled, [case()])['strict_hits'] == 1
    assert controlled.diagnostic_top50(case())[0].code == 'expected'
    assert seen == [(original_k, 1 / 11, ['query'], []), (50, 1 / 11, ['query'], [])]
    assert retrieve.CANDIDATE_K == original_k
    assert retrieve.rrf_fuse is original_fuse


def test_ab_pairs_change_exactly_one_variable():
    from scripts.rag_diagnose import ab_configurations
    pairs = ab_configurations(dict(rrf_k=60, top_k=3, rewrite=False, lexicon=True, offline=True))
    assert len(pairs) == 4
    for pair in pairs:
        assert sum(pair['baseline'][key] != pair['variant'][key]
                   for key in pair['baseline']) == 1


def test_cli_official_top3_and_single_variable_ab(monkeypatch, tmp_path, capsys):
    import json
    from backend.rag import retrieve
    from scripts.rag_diagnose import run_cli
    engine = StubRetriever(['acceptable', 'expected', 'other', 'fourth'])
    engine.rewriter = lambda q: [q]
    engine.search_vector = lambda *args: []
    monkeypatch.setattr(retrieve, 'default_retriever', lambda: engine)
    source = tmp_path / 'cases.json'
    source.write_text(json.dumps([case()]), encoding='utf-8')
    output = tmp_path / 'result.json'
    assert run_cli(['--cases', str(source), '--output', str(output),
                    '--top-k', '5', '--rewrite', 'off', '--ab']) == 0
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['official_top_k'] == 3
    assert result['strict_hits'] == 1
    assert result['exploratory']['top_k'] == 5
    assert len(result['ab']) == 3
    assert result['ab_skipped']
    assert all(pair[side]['official_top_k'] == 3 for pair in result['ab']
               for side in ('baseline', 'variant'))
    capsys.readouterr()


def test_response_cache_reuses_rewrite_and_vector_requests():
    from scripts.rag_diagnose import cached_requests
    calls = []
    engine = StubRetriever([])
    engine.rewriter = lambda q: calls.append(('rewrite', q)) or [q, 'expanded']
    engine.search_vector = lambda q, k, name='law_articles', where=None: calls.append((q, k)) or ['x']
    original = engine.rewriter
    with cached_requests(engine):
        assert engine.rewriter('q') == engine.rewriter('q')
        assert engine.search_vector('q', 10) == engine.search_vector('q', 10)
        engine.search_vector('q', 50)
    assert calls == [('rewrite', 'q'), ('q', 10), ('q', 50)]
    assert engine.rewriter is original


def test_empty_and_strict_success_metrics():
    assert evaluate(StubRetriever([]), [])['queries'] == 0
    result = evaluate(StubRetriever(['expected', 'acceptable']), [case()])
    assert result['strict_hits'] == result['relaxed_hits'] == 1
    assert result['partial_hits'] == 0
    assert result['article_precision'] == 0.5
    assert result['top1_accuracy'] == 1
