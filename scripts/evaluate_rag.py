"""运行冻结的真实话术查询集；报告法条召回及逐返回条号准确率。"""
import hashlib
import json
from pathlib import Path
from backend.rag.retrieve import default_retriever

CASES = Path(__file__).resolve().parents[1] / 'tests/rag/retrieval_cases.json'


def evaluate(retriever, cases):
    """不改 top_k；同时计算查询级召回、Top1 和逐条 precision。"""
    details = []
    for case in cases:
        hits = retriever.search(case['query'], top_k=3)
        codes = [hit.code for hit in hits]
        expected = set(case['expected_codes'])
        details.append({'id': case['id'], 'query': case['query'], 'codes': codes,
                        'hit': bool(expected.intersection(codes)),
                        'top1': bool(codes and codes[0] in expected),
                        'correct_returned': sum(code in expected for code in codes),
                        'returned': len(codes), 'status': dict(retriever.status),
                        'scores': [hit.score for hit in hits],
                        'routes': [hit.route for hit in hits]})
    total = len(details)
    recalled = sum(row['hit'] for row in details)
    correct = sum(row['correct_returned'] for row in details)
    returned = sum(row['returned'] for row in details)
    return {'recall_at_3': recalled / max(total, 1), 'recalled': recalled, 'queries': total,
            'article_accuracy': correct / max(returned, 1),
            'correct_returned': correct, 'returned': returned,
            'top1_accuracy': sum(row['top1'] for row in details) / max(total, 1),
            'details': details}


def main():
    """固定查询集读入后评测；保存实际运行结果供审计。"""
    cases = json.loads(CASES.read_text(encoding='utf-8'))
    retriever = default_retriever()
    result = evaluate(retriever, cases)
    result['frozen_sha256'] = hashlib.sha256(CASES.read_bytes()).hexdigest()
    result['independent_source_cases'] = len({row['source_case_id'] for row in cases})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    output = CASES.with_name('retrieval_report.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return int(result['recalled'] < 10)


if __name__ == '__main__':
    raise SystemExit(main())
