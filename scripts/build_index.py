"""构建法规索引；远程 embedding 不可用时明确失败，不伪造向量。"""
import logging
from collections import Counter
from backend.rag.ingest import load_laws, load_cases
from backend.rag.embedding import ChromaStore, EmbeddingError


def remove_stale(collection, records):
    """仅移除已不在归档输入里的索引 ID；不删除来源文件，成功 upsert 后调用。"""
    stale = sorted(set(collection.get(include=[])['ids']) - {r['id'] for r in records})
    if stale:
        print('移除陈旧索引 ID: ' + ', '.join(stale))
        collection.delete(ids=stale)


def main():
    """解析、入库、读回计数；返回非零表示索引尚未建成。"""
    laws, skipped = load_laws()
    cases = load_cases()
    lengths = [len(row['text']) for row in laws]
    print(f'解析 law_articles: {len(laws)} 条（decision 子块 {len(laws)} / 父块内嵌）')
    print(f'解析 case_fines: {len(cases)} 条')
    print(f'跳过 procedure: {skipped} 条')
    print(f'平均子块长度 / 最长 / 最短: {sum(lengths)/max(len(lengths),1):.2f}'
          f' / {max(lengths,default=0)} / {min(lengths,default=0)}')
    try:
        store = ChromaStore()
        store.upsert('law_articles', laws)
        store.upsert('case_fines', cases)
        remove_stale(store.collections['law_articles'], laws)
        remove_stale(store.collections['case_fines'], cases)
        print(f"law_articles: {store.count('law_articles')} 条（已读回）")
        print(f"case_fines: {store.count('case_fines')} 条（已读回）")
        persisted = store.collections['law_articles'].get(include=['metadatas'])['metadatas']
        distribution = Counter(row.get('domain', 'missing') for row in persisted)
        print('domain distribution (persisted): ' + ' / '.join(
            f'{name}={distribution[name]}' for name in
            ('medical', 'general', 'agriculture', 'tobacco_alcohol', 'realestate_edu', 'minor_media')))
        if store.count('case_fines') != 11:
            print('STOP: case_fines.count() != 11；不得继续评测')
            return 1
    except EmbeddingError as exc:
        print(f'入库失败: {exc}；未生成替代向量，检索可降级 BM25')
        return 1
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
