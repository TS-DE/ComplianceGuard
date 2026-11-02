"""Read-only retrieval diagnostics. Precedence: A, B, C, D, E, explicit gap.

Top50 widens diagnostic candidates only; official metrics remain Top3.
Collection absence is established only by a successful collection.get.
"""
import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from backend.rag import retrieve
from backend.rag.embedding import EmbeddingError
from scripts.evaluate_rag import CASES, LEXICON, evaluate


@contextmanager
def cached_requests(retriever):
    """Freeze successful live responses within an A/B run; missing keys call real adapters.

    Candidate count and filters are part of the key: Top50 never pollutes Top10.
    Failures are not fabricated or cached. This contains no credentials.
    """
    rewrites, vectors = {}, {}
    rewrite, vector = retriever.rewriter, retriever.search_vector

    def cached_rewrite(text):
        if text not in rewrites:
            rewrites[text] = list(rewrite(text))
        return list(rewrites[text])

    def cached_vector(q, k, name='law_articles', where=None):
        key = (q, k, name, json.dumps(where, sort_keys=True))
        if key not in vectors:
            vectors[key] = list(vector(q, k, name, where))
        return list(vectors[key])

    with patch.object(retriever, 'rewriter', cached_rewrite), patch.object(
            retriever, 'search_vector', cached_vector):
        yield


class ControlledRetriever:
    """Serial script-only experiments; context patches are always restored.

    Do not use concurrently with production requests. No index writes occur.
    Default settings preserve live production rewrite and vector retrieval.
    """
    def __init__(self, retriever, *, rrf_k=60, rewrite=True, lexicon=True, offline=False):
        self.base = retriever
        self.config = dict(rrf_k=rrf_k, rewrite=rewrite, lexicon=lexicon, offline=offline)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def _search(self, query, top_k, axis, candidate_k=None):
        original_fuse = retrieve.rrf_fuse
        with ExitStack() as stack:
            stack.enter_context(patch.object(retrieve, 'rrf_fuse',
                side_effect=lambda ranks: original_fuse(ranks, k=self.config['rrf_k'])))
            if candidate_k is not None:
                stack.enter_context(patch.object(retrieve, 'CANDIDATE_K', candidate_k))
            if not self.config['rewrite']:
                stack.enter_context(patch.object(self.base, 'rewriter', lambda text: [text]))
            if not self.config['lexicon']:
                stack.enter_context(patch.object(retrieve, 'expand_by_lexicon', lambda text: []))
            if self.config['offline']:
                stack.enter_context(patch.object(self.base, 'search_vector',
                    side_effect=EmbeddingError('offline: vector disabled')))
            return self.base.search(query, top_k=top_k, axis=axis)

    def search(self, query, top_k=3, axis=None):
        return self._search(query, top_k, axis)

    def diagnostic_top50(self, row):
        status = dict(self.base.status)
        case_hits = getattr(self.base, 'case_hits', None)
        try:
            return self._search(row['query'], 50, row['violation_type'], candidate_k=50)
        finally:
            self.base.status = status
            if case_hits is not None:
                self.base.case_hits = case_hits


def ab_configurations(config):
    """Four paired comparisons (2×N), each differing in one control only."""
    alternatives = dict(rrf_k=10 if config['rrf_k'] != 10 else 60,
                        top_k=5 if config['top_k'] != 5 else 3,
                        rewrite=not config['rewrite'], lexicon=not config['lexicon'])
    return [dict(variable=key, baseline=dict(config), variant={**config, key: value})
            for key, value in alternatives.items()]


def _run(retriever, cases, config, lexicon):
    controlled = ControlledRetriever(retriever, **{k: v for k, v in config.items() if k != 'top_k'})
    result = evaluate(controlled, cases, lexicon=lexicon)
    result['configuration'] = config
    result['failures'] = diagnose_failures(controlled, result, lexicon=lexicon,
                                          top50_search=controlled.diagnostic_top50)
    result['failure_counts'] = {category: sum(r['category'] == category for r in result['failures'])
                                for category in ('A', 'B', 'C', 'D', 'E', 'unclassified')}
    # --top-k is exploratory output, never the official metric denominator.
    if config['top_k'] != 3:
        result['exploratory'] = dict(top_k=config['top_k'], details=[
            dict(id=c['id'], codes=[h.code for h in controlled.search(
                c['query'], top_k=config['top_k'], axis=c['violation_type'])]) for c in cases])
    return result


def run_cli(argv=None, default_output=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=CASES)
    parser.add_argument('--output', type=Path, default=default_output)
    parser.add_argument('--rrf-k', type=int, default=60)
    parser.add_argument('--top-k', type=int, choices=range(1, 11), default=3)
    parser.add_argument('--rewrite', choices=('on', 'off'), default='on')
    parser.add_argument('--lexicon', choices=('on', 'off'), default='on')
    parser.add_argument('--offline', action='store_true', help='Disable vector network calls; also use --rewrite off for a fully offline run.')
    parser.add_argument('--ab', action='store_true', help='Run four paired single-variable comparisons (2×4 runs).')
    args = parser.parse_args(argv)
    if args.rrf_k < 0:
        parser.error('--rrf-k must be nonnegative')
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    lexicon = json.loads(LEXICON.read_text(encoding='utf-8'))
    retriever = retrieve.default_retriever()
    config = dict(rrf_k=args.rrf_k, top_k=args.top_k,
                  rewrite=args.rewrite == 'on', lexicon=args.lexicon == 'on', offline=args.offline)
    with cached_requests(retriever):
        result = _run(retriever, cases, config, lexicon)
        if args.ab:
            result['ab'] = [dict(variable=p['variable'],
                baseline=_run(retriever, cases, p['baseline'], lexicon),
                variant=_run(retriever, cases, p['variant'], lexicon))
                for p in ab_configurations(config) if p['variable'] != 'top_k']
            result['ab_skipped'] = ['top_k: 本轮禁止调整；仅提供显式诊断开关，官方固定3']
    result['frozen_sha256'] = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    result['independent_source_cases'] = len({r['source_case_id'] for r in cases})
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf-8')
    return 0


def diagnose_failures(retriever, result, *, lexicon=None, top50_search=None):
    lexicon = lexicon if lexicon is not None else json.loads(LEXICON.read_text(encoding='utf-8'))
    collection = None
    try:
        collection = retriever.vector.client.get_collection('law_articles')
    except Exception:
        pass  # Never label unavailable collection as absent expected article.
    failures = []
    for row in result['details']:
        if row['hit']:
            continue
        expected = set(row['expected_codes'])
        acceptable_hits = sorted(set(row.get('acceptable_codes', [])) & set(row['codes']))
        evidence, inspection = {}, 'available' if collection is not None else 'unavailable'
        for code in sorted(expected):
            if collection is None:
                continue
            try:
                found = collection.get(where={'code': code})
                evidence[code] = dict(count=len(found['ids']), metadata=found.get('metadatas') or [])
            except Exception:
                inspection = 'incomplete'
        domains = {'medical', 'general', 'realestate_edu'} if row['violation_type'] == 'endorsement' else {'medical', 'general'}
        absent = [c for c, e in evidence.items() if not e['count']]
        filtered = [c for c, e in evidence.items() if e['count'] and e['metadata'] and
                    all(m.get('relevance') != 'decision' or m.get('domain', 'general') not in domains
                        for m in e['metadata'])]
        top50, top50_state = [], 'not_requested'
        if top50_search is not None:
            try:
                top50 = [getattr(h, 'code', h) for h in top50_search(row)]
                top50_state = 'available'
            except Exception:
                top50_state = 'unavailable'
        coverage = lexicon.get(row['violation_type'], {}).get('coverage', 'insufficient')
        category, reason, remedy = 'unclassified', 'Diagnostic gap: available evidence fits none of A–E.', 'Inspect query intent, candidate recall and ranking traces; do not relabel the case.'
        if acceptable_hits:
            category, reason, remedy = 'A', 'Human-declared acceptable annotation actually hit: ' + ', '.join(acceptable_hits), 'Review the declared annotation ambiguity; retain strict failure and report relaxed hit separately.'
        elif expected and len(absent) == len(expected):
            category, reason, remedy = 'B', 'Expected articles absent from collection.get results.', 'Review ingestion and rebuild the law index with the missing articles.'
        elif expected and set(absent + filtered) == expected and filtered:
            category, reason, remedy = 'C', 'Present expected articles disallowed by domain/relevance filters.', 'Review article domain/relevance metadata; retain legitimate legal scope restrictions.'
        elif expected.intersection(top50):
            category, reason, remedy = 'D', 'Expected article appears in diagnostic Top50 but not official Top3.', 'Investigate candidate ranking; compare a single variable without changing official Top3.'
        elif coverage in ('insufficient', 'no_case'):
            category, reason, remedy = 'E', 'Violation-type lexicon coverage is ' + coverage + '.', 'Add source-backed colloquial terms and independent cases; do not invent labels.'
        failures.append(dict(id=row['id'], query=row['query'], expected_codes=row['expected_codes'],
            actual_codes=row['codes'], category=category, reason=reason, remedy=remedy,
            acceptable_hits=acceptable_hits, collection_inspection=inspection,
            collection_evidence=evidence, absent_codes=absent, filtered_codes=filtered,
            top50_codes=top50, top50_inspection=top50_state, lexicon_coverage=coverage))
    return failures


if __name__ == '__main__':
    raise SystemExit(run_cli())
