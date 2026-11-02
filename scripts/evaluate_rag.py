"""Frozen-query evaluation; strict official metrics always use Top3."""
import hashlib
import json
from pathlib import Path
from backend.rag.retrieve import default_retriever

CASES = Path(__file__).resolve().parents[1] / 'tests/rag/retrieval_cases.json'
LEXICON = CASES.parents[2] / 'data/lexicon/synonyms.json'


def _metrics(rows):
    total = len(rows)
    strict = sum(row['hit'] for row in rows)
    relaxed = sum(row['relaxed_hit'] for row in rows)
    partial = sum(row['partial_hit'] for row in rows)
    returned = sum(row['returned'] for row in rows)
    correct = sum(row['correct_returned'] for row in rows)
    relaxed_correct = sum(row['relaxed_correct_returned'] for row in rows)
    top1 = sum(row['top1'] for row in rows)
    return dict(queries=total, recalled=strict, strict_hits=strict,
                relaxed_hits=relaxed, partial_hits=partial,
                recall_at_3=strict / max(total, 1),
                strict_recall_at_3=strict / max(total, 1),
                relaxed_recall_at_3=relaxed / max(total, 1),
                partial_rate=partial / max(total, 1),
                top1=top1, top1_accuracy=top1 / max(total, 1),
                correct_returned=correct, returned=returned,
                article_accuracy=correct / max(returned, 1),
                article_precision=correct / max(returned, 1),
                relaxed_article_precision=relaxed_correct / max(returned, 1))


def evaluate(retriever, cases, *, lexicon=None):
    """Compatible API; acceptable-only hits never inflate strict metrics."""
    details = []
    lexicon = lexicon if lexicon is not None else json.loads(LEXICON.read_text(encoding='utf-8'))
    for case in cases:
        hits = retriever.search(case['query'], top_k=3, axis=case['violation_type'])
        codes = [hit.code for hit in hits]
        expected = set(case['expected_codes'])
        acceptable = set(case.get('acceptable_codes', []))
        strict = bool(expected.intersection(codes))
        relaxed = bool((expected | acceptable).intersection(codes))
        details.append(dict(id=case['id'], query=case['query'], codes=codes,
            expected_codes=case['expected_codes'], acceptable_codes=sorted(acceptable),
            expected_basis=case.get('expected_basis', ''),
            violation_type=case['violation_type'], source_case_id=case.get('source_case_id'),
            hit=strict, strict_hit=strict, relaxed_hit=relaxed,
            partial_hit=relaxed and not strict,
            top1=bool(codes and codes[0] in expected),
            correct_returned=sum(code in expected for code in codes),
            relaxed_correct_returned=sum(code in expected | acceptable for code in codes),
            returned=len(codes), status=dict(retriever.status),
            scores=[hit.score for hit in hits], routes=[hit.route for hit in hits]))
    by_type = {}
    for kind in sorted({row['violation_type'] for row in details}):
        entry = lexicon.get(kind, {})
        coverage = entry.get('coverage', 'insufficient' if len(entry.get('terms', [])) < 3 else 'ok')
        by_type[kind] = {**_metrics([r for r in details if r['violation_type'] == kind]),
                         'coverage': coverage,
                         'note': '该类词表不足，检索结论不可用' if coverage != 'ok' else ''}
    return {**_metrics(details), 'official_top_k': 3, 'by_type': by_type,
            'uncovered': sorted(k for k, e in lexicon.items() if e.get('coverage') != 'ok'),
            'details': details}


def main(argv=None):
    # Shared CLI keeps experimental controls out of production retrieval.
    from scripts.rag_diagnose import run_cli
    return run_cli(argv, default_output=CASES.with_name('retrieval_report.json'))


if __name__ == '__main__':
    raise SystemExit(main())
