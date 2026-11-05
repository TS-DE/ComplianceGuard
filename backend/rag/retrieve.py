"""BM25、向量秩融合与可观察的降级；业务只依赖检索抽象。"""
import json
import logging
import math
import re
from pathlib import Path
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
import jieba
from backend.rag.embedding import (
    DashScopeEmbeddingFunction, EmbeddingError, llm_config, pin_jieba_cache)

logger = logging.getLogger(__name__)
RRF_K = 60
CANDIDATE_K = 10
MIN_SCORE = 0.01
BM25_K1 = 1.5
BM25_B = 0.75
LAW_TERMS = ('绝对化用语', '保证性承诺', '疗效断言', '医疗美容', '广告审查', '贬低同行', '容貌焦虑')


# jieba 的缓存必须先钉到项目盘再碰词典，否则第一个 add_word 就会按默认路径建缓存
pin_jieba_cache()
for term in LAW_TERMS:
    jieba.add_word(term)


@dataclass
class Hit:
    code: str
    text: str
    parent_text: str
    doc_type: str
    score: float
    route: str
    source: str = ''
    chunk_id: str = ''
    item_no: str | None = None


class VectorIndex(Protocol):
    def query(self, name: str, text: str, k: int, where=None) -> list[str]: ...


class Retriever(ABC):
    @abstractmethod
    def search(self, text: str, top_k: int = 3, doc_type=None) -> list[Hit]: ...


class BM25:
    """保留全部分词，便于从词频和长度复现分数。"""

    def __init__(self, records):
        self.records = records
        self.tokens = [Counter(jieba.cut_for_search(row['text'])) for row in records]
        self.lengths = [sum(tokens.values()) for tokens in self.tokens]
        self.average = sum(self.lengths) / max(len(records), 1)
        self.df = Counter(term for tokens in self.tokens for term in tokens)

    def search(self, query, k, allowed=None):
        scores = []
        for row, tokens, length in zip(self.records, self.tokens, self.lengths):
            if allowed is not None and row['id'] not in allowed:
                continue
            score = 0.0
            for term in jieba.cut_for_search(query):
                freq = tokens[term]
                if not freq:
                    continue
                idf = math.log(1 + (len(self.records) - self.df[term] + 0.5)
                               / (self.df[term] + 0.5))
                denominator = freq + BM25_K1 * (1 - BM25_B + BM25_B * length / self.average)
                score += idf * freq * (BM25_K1 + 1) / denominator
            if score > 0:
                scores.append((row['id'], score))
        return [key for key, _ in sorted(scores, key=lambda pair: (-pair[1], pair[0]))[:k]]


def rrf_fuse(rank_lists, k=RRF_K):
    """仅用各路名次融合，不混用 BM25 与余弦量纲。"""
    scores = Counter()
    for ranks in rank_lists:
        for rank, key in enumerate(dict.fromkeys(ranks), 1):
            scores[key] += 1 / (k + rank)
    return dict(scores)


def expand_by_lexicon(text):
    """命中可追溯口语词后追加法规术语；不生成原话或法条。"""
    path = Path(__file__).resolve().parents[2] / 'data/lexicon/synonyms.json'
    lexicon = json.loads(path.read_text(encoding='utf-8'))
    queries = []
    for entry in lexicon.values():
        if any(term in text for term in entry['terms']):
            queries.extend(entry['queries'])
    return list(dict.fromkeys(queries))


def rewrite_query(text):
    """一次 LLM 调用提炼检索词；失败退回原话术，不生成法条。"""
    config = llm_config()
    if not config.get('JUDGE_API_KEY'):
        logger.warning('query_rewrite_unavailable: 缺少 JUDGE_API_KEY')
        return [text]
    client = DashScopeEmbeddingFunction()
    try:
        result = client._request('/chat/completions', {
            'model': config.get('JUDGE_MODEL', 'qwen-plus'), 'temperature': 0,
            'messages': [{'role': 'system', 'content':
                '把营销话术提炼为2至4个违规类型检索词。只返回JSON字符串数组。'
                '考虑功效安全性断言、保证性承诺、医疗广告、绝对化用语、虚假广告、'
                '容貌焦虑、代言证明、豁免情形。不判断合法性，不编造法条或条号。'},
                {'role': 'user', 'content': text}]})
        words = json.loads(result['choices'][0]['message']['content'])
        if not isinstance(words, list) or not words or not all(isinstance(w, str) for w in words):
            raise ValueError('invalid rewrite')
        return [text, *words[:4]]
    except (EmbeddingError, KeyError, ValueError, TypeError):
        logger.warning('query_rewrite_failed: 使用原话术')
        return [text]


class HybridRetriever(Retriever):
    """组合词法索引与向量抽象；两集合独立排序，不混为法律依据。"""

    def __init__(self, laws, cases, vector: VectorIndex | None, rewriter=rewrite_query):
        self.groups = {'law_articles': laws, 'case_fines': cases}
        self.bm25 = {name: BM25(rows) for name, rows in self.groups.items()}
        self.vector, self.rewriter = vector, rewriter
        self.status = {}
        self.case_hits = []

    def search_bm25(self, q, k, name='law_articles', allowed=None):
        return self.bm25[name].search(q, k, allowed)

    def search_vector(self, q, k, name='law_articles', where=None):
        if self.vector is None:
            raise EmbeddingError('向量索引不可用')
        return self.vector.query(name, q, k, where)

    def _ranks(self, queries, name, doc_type, domains):
        rows = self.groups[name]
        allowed = {r['id'] for r in rows if r['metadata'].get('relevance') == 'decision'
                   and (doc_type is None or r['metadata']['doc_type'] == doc_type)
                   and (name != 'law_articles' or r['metadata'].get('domain', 'general') in domains)}
        where = {'relevance': 'decision'}
        if name == 'law_articles':
            self.status['filtered_codes'] = sorted({r['metadata']['code'] for r in rows
                if r['metadata'].get('domain', 'general') not in domains})
            where = {'$and': [where, {'domain': {'$in': list(domains)}}]}
        if doc_type:
            where = {'$and': [where, {'doc_type': doc_type}]}
        ranks, routes = [], {}
        vector_ok = True
        for query in queries:
            bm = self.search_bm25(query, CANDIDATE_K, name, allowed)
            ranks.append(bm)
            for key in bm:
                routes.setdefault(key, set()).add('bm25')
            if not vector_ok:
                continue
            try:
                vec = self.search_vector(query, CANDIDATE_K, name, where)
                ranks.append([key for key in vec if key in allowed])
                for key in vec:
                    routes.setdefault(key, set()).add('vector')
            except Exception:
                vector_ok = False
                self.status['degraded'] = 'vector_unavailable'
                logger.warning('vector_unavailable: 已降级 BM25')
        return ranks, routes

    def _search_group(self, queries, name, top_k, doc_type, law_articles, domains=()):
        ranks, routes = self._ranks(queries, name, doc_type, domains)
        scores = rrf_fuse(ranks)
        indexed = {row['id']: row for row in self.groups[name]}
        candidates = sorted(scores, key=lambda key: -scores[key])[:CANDIDATE_K]
        hits = []
        for key in candidates:
            row, score = indexed[key], scores[key]
            meta, content = row['metadata'], row['text']
            # RRF 是置信兜底口径，规则加分只用于候选重排，不可制造匹配。
            bonus = 2 * any(word in content for word in ('不得', '禁止', '严禁'))
            bonus += 3 * (meta['code'] in law_articles)
            bonus -= int(len(content) > 300)
            bonus += int('不适用' in content or '不构成广告' in content)
            # 数字/规模是检索线索，不是违法判定；仅提升已召回的28条(二)，不注入候选。
            if (name == 'law_articles' and meta['code'] == '广告法第28条'
                    and '与实际情况不符' in content
                    and re.search(r'\d|[一二三四五六七八九十百千万亿]+(?:多|个|家|年|月|人|次)', queries[0])):
                bonus += 3
            route = '+'.join(sorted(routes.get(key, [])))
            if self.status.get('lexicon'):
                route += '+lexicon'
            if self.status.get('rewrite'):
                route += '+rewrite'
            if self.status.get('degraded'):
                route += ';degraded=vector_unavailable'
            # code 已是独立字段；只在输出边界去掉合成前缀，不改索引或归档原文。
            body = content.removeprefix(meta['code'] + '\n') if name == 'law_articles' else content
            hit = Hit(meta['code'], body, meta.get('parent_text', body),
                      meta['doc_type'], score, route, meta.get('source', ''), key, meta.get('item_no'))
            hits.append((bonus, score, hit))
        if not hits or max(h[1] for h in hits) < MIN_SCORE:
            self.status['no_reference'] = True
            return []
        hits.sort(key=lambda row: (-row[0], -row[1], row[2].code))
        unique = {}
        for _, _, hit in hits:
            unique.setdefault(hit.code, hit)
        return list(unique.values())[:top_k]

    def search(self, text, top_k=3, doc_type=None, law_articles=(), axis=None):
        """返回法律依据；case_hits 独立暴露；故障状态不等于合规。"""
        if not 1 <= top_k <= CANDIDATE_K:
            raise ValueError('top_k 必须为 1..10')
        self.status, self.case_hits = {}, []
        try:
            try:
                queries = self.rewriter(text)
            except Exception:
                queries = [text]
                self.status['rewrite_failed'] = True
            expanded = expand_by_lexicon(text)
            self.status['lexicon'] = bool(expanded)
            self.status['rewrite'] = any(q != text for q in queries)
            queries = list(dict.fromkeys([text, *expanded, *queries]))
            domains = ('medical', 'general', 'realestate_edu') if axis == 'endorsement' else ('medical', 'general')
            laws = self._search_group(queries, 'law_articles', top_k, doc_type, law_articles, domains)
            self.case_hits = self._search_group(queries, 'case_fines', top_k, None, ())
            return laws
        except Exception:
            self.status.update(retrieval_error=True, incomplete=True)
            logger.exception('retrieval_error: 检索未完成')
            return []


@lru_cache(maxsize=1)
def default_retriever():
    """在组合根注入基础设施；service/agent 无需导入 Chroma。"""
    from backend.rag.ingest import load_laws, load_cases
    from backend.rag.embedding import ChromaStore
    laws, _ = load_laws()
    try:
        store = ChromaStore()
    except Exception:
        logger.warning('vector_store_unavailable: 使用 BM25')
        store = None
    return HybridRetriever(laws, load_cases(), store)


def search(text, top_k=3, doc_type=None, axis=None):
    return default_retriever().search(text, top_k, doc_type, axis=axis)
