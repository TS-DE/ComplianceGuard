"""审查流水线使用可控边界，验证证据而非模型评分。"""
import json
import pytest
from backend.agents.base import Detector, ChatModel


class ResponseModel(ChatModel):
    def __init__(self, content): self.content = content
    def complete(self, messages):
        return dict(content=json.dumps(self.content, ensure_ascii=False), model='test',
                    prompt_tokens=5, completion_tokens=2, cost=0.001)


def audit(text, hits, exemptions=None):
    from backend.agents.compliance import ComplianceAuditAgent
    model = ResponseModel({'hits': hits})
    rules = [dict(axis='absolute_terms', pattern='绝对化', law_article='广告法第9条',
                  exemptions=exemptions, detector='llm_judge')]
    return ComplianceAuditAgent(lambda: rules,
        lambda q: [dict(code='广告法第9条', text='不得最佳')], model).review(text)


@pytest.fixture(params=[[], [dict(axis='efficacy_claim', enabled=False)]])
def empty_rules(request):
    return request.param


def test_no_rules_yields_incomplete(empty_rules):
    from backend.agents.compliance import ComplianceAuditAgent
    result = ComplianceAuditAgent(lambda: empty_rules, lambda q: [], None).review('介绍服务')
    assert result['score'] == -1
    assert result['incomplete'] is True
    assert result['reason'] == 'no_rules_loaded'


def test_all_detectors_failing_yields_incomplete():
    from backend.agents.compliance import ComplianceAuditAgent

    class BrokenDetector(Detector):
        def detect(self, text, rule):
            raise RuntimeError('offline')

    rules = [dict(axis=axis, detector='broken') for axis in ('efficacy_claim', 'safety_guarantee')]
    result = ComplianceAuditAgent(lambda: rules, lambda q: [], None,
                                 {'broken': BrokenDetector()}).review('介绍服务')
    assert result['score'] == -1 and result['incomplete'] is True
    assert len([t for t in result['traces'] if t['status'] == 'axis_failed']) == 2


def test_fabricated_quote_discarded():
    r = audit('正常介绍', [dict(quote='编造', law_article='广告法第9条', reason='x')])
    assert r['hits'] == []
    assert r['traces'][0]['status'] == 'invalid_quote'


def test_out_of_axis_citation_discarded_not_gap():
    """作者裁决（2026-11-06）：轴声明法源后，模型引用只验轴。
    引用不在本轴声明集合（第999条 vs 声明的第9条）= 越轴引证：
    丢弃该命中记 law_out_of_axis，**不记 evidence_gap**——模型乱引
    不能把整条判成"未完成"。旧契约（invalid_law_ref+证据缺口）被推翻。"""
    r = audit('最佳', [dict(quote='最佳', law_article='广告法第999条', reason='x')])
    assert r['hits'] == []
    assert r['traces'][0]['status'] == 'law_out_of_axis'
    assert r['incomplete'] is False


def test_declared_axis_law_binds_from_rule_table_without_retrieval():
    """轴声明法源 → 绑定走规则表，检索候选缺位不再翻转结论（s33 根因）。
    命中引用与声明匹配（第9条），检索只有别的法条：命中保留、无 evidence_gap。"""
    from backend.agents.compliance import ComplianceAuditAgent
    model = ResponseModel({'hits': [dict(quote='热玛吉可以除去皱纹',
                                        law_article='广告法第9条', reason='x')]})
    rules = [dict(axis='absolute_terms', pattern='绝对化', law_article='广告法第9条',
                  detector='llm_judge')]
    r = ComplianceAuditAgent(lambda: rules, lambda q: [dict(code='广告法第16条')],
                             model).review('热玛吉可以除去皱纹')
    assert r['incomplete'] is False
    assert r['score'] == 0, "规则表绑定成功：不得因检索抖动记 -1 或放行"
    assert any(t['status'] == 'law_from_rule_table' for t in r['traces'])


def test_search_law_is_cached_for_same_text(monkeypatch):
    """同一句话在同一进程内必须拿到同一批候选，否则结论无法复现。"""
    from backend.mcp_server import server as mcp_server
    from backend.tools.audit_tool import _cached_law_lookup, search_law

    calls = {"n": 0}

    def fake_search(query, top_k=3):
        calls["n"] += 1
        return [dict(code='广告法第16条', text=query, chunk_id=f'c{calls["n"]}')]

    monkeypatch.setattr(mcp_server, "rag_search_law", fake_search)
    _cached_law_lookup.cache_clear()

    first = search_law("同一句话术")
    second = search_law("同一句话术")
    assert calls["n"] == 1, "第二次调用应命中缓存，不重复检索"
    assert first == second
    assert first[0]["chunk_id"] == second[0]["chunk_id"]

    # 调用方就地修改返回值不得污染缓存
    first[0]["code"] = "被改坏"
    assert search_law("同一句话术")[0]["code"] == "广告法第16条"
    _cached_law_lookup.cache_clear()


def test_descriptive_prognosis_is_downgraded_not_cleared():
    """预后描述应降级为"疑似"，既不能判违规，也不能直接放行。

    实测背景：模型把「皮肤愈合后，应更显光滑」判成功效断言。
    这句是愈合后的常规预后描述，没有向顾客承诺确定结果。
    正确处理是保留命中但降为 soft：界面显示"疑似违规 · 建议复核"，
    商家仍被提示有风险，又不至于把正常宣传一刀切判死。
    """
    text = "皮肤愈合后，应更显光滑"
    r = audit(text, [dict(quote=text, law_article="广告法第9条", reason="x")])
    assert r["hit_count"] == 1, "命中必须保留，降级不等于放行"
    assert r["hits"][0]["downgraded"] is True
    assert r["hits"][0]["severity"] == "soft"
    assert "模糊限定词" in r["hits"][0]["downgrade_reason"]
    assert r["score"] == 1, "降级后应为疑似(1)，不是违规(0)，也不是合规(2)"


def test_recovery_period_with_modifiers_is_downgraded():
    """「可能需要大约三个月才能恢复正常肤色」是恢复周期告知，不是疗效承诺。"""
    text = "可能需要大约三个月时间才能恢复正常肤色"
    r = audit(text, [dict(quote=text, law_article="广告法第9条", reason="x")])
    assert r["hits"][0]["downgraded"] is True
    assert r["score"] == 1


def test_commitment_phrase_stays_hard():
    """去掉限定词、变成打包票的同一信息必须保持硬命中。"""
    text = "保证三个月恢复正常肤色"
    r = audit(text, [dict(quote=text, law_article="广告法第9条", reason="x")])
    assert r["score"] == 0
    assert r["hits"][0].get("downgraded") is not True


def test_two_downgraded_hits_do_not_sum_to_violation():
    """两句独立的预后描述不能凑成"多处违规"，否则降级就白做了。"""
    text = "皮肤愈合后应更显光滑。可能需要大约三个月恢复正常肤色"
    hits = [dict(quote="皮肤愈合后应更显光滑", law_article="广告法第9条", reason="x"),
            dict(quote="可能需要大约三个月恢复正常肤色", law_article="广告法第9条", reason="y")]
    r = audit(text, hits)
    assert all(h["downgraded"] for h in r["hits"])
    assert r["score"] == 1


def test_exemption_retained_as_trace_not_active_hit():
    exemption = dict(text='仅表明服务态度或者经营理念、主观愿望的', source='指南第五条(一)')
    r = audit('我们要做最好的医美服务',
              [dict(quote='最好', law_article='广告法第9条', reason='x')], [exemption])
    assert r['score'] == 2 and r['hit_count'] == 0
    assert r['traces'][0]['exempted_by'] == exemption


def test_exemption_does_not_cover_effect_guarantee():
    exemption = dict(text='仅表明经营理念、主观愿望的', source='指南第五条(一)')
    r = audit('我们要做最好的医美服务，保证一次见效',
              [dict(quote='最好', law_article='广告法第9条', reason='x')], [exemption])
    assert r['score'] == 0


def test_unknown_detector_is_incomplete():
    from backend.agents.compliance import ComplianceAuditAgent
    r = ComplianceAuditAgent(lambda: [dict(detector='unknown', axis='new')], lambda q: [], None).review('test')
    assert r['score'] == -1 and r['incomplete']


def test_retrieval_failure_does_not_skip_semantic_call():
    from backend.agents.compliance import ComplianceAuditAgent
    class Model(ResponseModel):
        calls = 0
        def complete(self, messages):
            self.calls += 1
            return super().complete(messages)
    model = Model({'hits': []})
    def search(q): raise RuntimeError('offline')
    r = ComplianceAuditAgent(lambda: [dict(axis='efficacy_claim')], search, model).review('介绍服务')
    assert model.calls == 1
    assert r['no_reference'] and not r['incomplete']


@pytest.mark.parametrize('score,hits,incomplete,passed', [(2,0,False,True),(0,1,False,True),
                          (0,2,False,False),(-1,0,True,False)])
def test_rewrite_always_rechecks_and_never_passes_incomplete(score,hits,incomplete,passed):
    from backend.agents.compliance import RewriteAgent
    class Auditor:
        calls = []
        def review(self, text, client_id=None):
            self.calls.append(text)
            return dict(score=score, hit_count=hits, incomplete=incomplete)
    auditor = Auditor()
    r = RewriteAgent(auditor, ResponseModel({'rewrites':['修订稿']})).rewrite(
        '原稿', [dict(sentence_id=0), dict(sentence_id=1)])
    assert auditor.calls == ['修订稿']
    assert r['rewrite_passed'] == passed
    assert r['rewritten_text'] == '修订稿'


def test_judge_prompt_requires_exact_retrieved_code_not_rule_subitem():
    from backend.agents.base import LLMJudgeDetector, Rule
    class Capture(ResponseModel):
        def complete(self, messages):
            assert '逐字复制' in messages[0]['content']
            payload = json.loads(messages[1]['content'])
            assert 'law_article' not in payload
            return super().complete(messages)
    detector = LLMJudgeDetector(Capture({'hits':[]}))
    assert detector.detect('保证有效', Rule(law_article='广告法第16条(一)',
        law_refs=[dict(code='广告法第16条')])) == []


def test_soft_sentence_aggregation_and_failed_axis():
    from backend.agents.compliance import _score
    assert _score([dict(severity='soft',sentence_id=0),dict(severity='soft',sentence_id=0)]) == 1
    assert _score([dict(severity='soft',sentence_id=0),dict(severity='soft',sentence_id=1)]) == 0


def test_scope_constant_applied_only_with_supported_model_evidence():
    from backend.agents.compliance import ComplianceAuditAgent
    from backend.core.constants import SCOPE_EXEMPTIONS
    # 不以“科研”一词机械豁免推广，模型须引用逐字证据并只选现有开关。
    model = ResponseModel({'scope_exemption': 'scope_01', 'quote': '临床研究招募受试者'})
    agent = ComplianceAuditAgent(lambda: [dict(axis='efficacy_claim')], lambda q: [], model)
    r = agent.review('本院临床研究招募受试者')
    assert r['scope_exempted_by'] == SCOPE_EXEMPTIONS[0]
    assert r['score'] == 2


def test_regex_best_service_reaches_exemption():
    from backend.agents.compliance import ComplianceAuditAgent
    exemption = dict(text='仅表明经营理念、主观愿望的', source='指南第五条(一)')
    r = ComplianceAuditAgent(lambda: [dict(axis='absolute_terms', detector='regex',
        law_article='广告法第9条', exemptions=[exemption])],
        lambda q: [dict(code='广告法第9条')], None).review('我们要做最好的医美服务')
    assert r['score'] == 2
    assert r['traces'][0]['status'] == 'exempted'


def test_cheap_rule_item_maps_only_to_retrieved_parent_code():
    from backend.agents.compliance import ComplianceAuditAgent
    r = ComplianceAuditAgent(lambda: [dict(axis='absolute_terms', detector='regex',
        law_article='广告法第9条(三)')],
        lambda q: [dict(code='广告法第9条')], None).review('顶级机构')
    assert r['score'] == 0
    assert r['hits'][0]['law_article'] == '广告法第9条'


def test_transient_chat_transport_retries_without_fabricating_usage():
    from backend.tools.audit_tool import UrllibChatModel
    from backend.rag.embedding import EmbeddingError
    calls = []
    def transport(path, payload):
        calls.append(path)
        if len(calls) == 1: raise EmbeddingError('temporary')
        return dict(choices=[dict(message=dict(content='{"hits":[]}'))],
                    usage=dict(prompt_tokens=4, completion_tokens=2))
    result = UrllibChatModel(transport).complete([])
    assert len(calls) == 2
    assert result['prompt_tokens'] == 4


def test_normalization_maps_expansion_whitespace_and_zero_width():
    from backend.agents.compliance import normalize_text
    text, offsets = normalize_text('Ａ\u200b  B\nＣ')
    assert text == 'A B C'
    assert offsets[0] == (0, 1)
    assert offsets[-1] == (6, 7)


def test_cheap_detection_runs_before_retrieval_then_semantics():
    from backend.agents.compliance import ComplianceAuditAgent
    events = []
    class Probe(Detector):
        def __init__(self, name): self.name = name
        def detect(self, text, rule):
            events.append(self.name)
            return [dict(quote='保证有效', law_article='广告法第16条')]
    rules = [dict(axis='efficacy_claim', detector='llm_judge'),
             dict(axis='safety_guarantee', detector='keyword',law_article='广告法第16条')]
    def search(query):
        events.append('rag')
        return [dict(code='广告法第16条', text='不得保证疗效')]
    agent = ComplianceAuditAgent(lambda: rules, search, None,
        detectors={'keyword': Probe('cheap'), 'llm_judge': Probe('semantic')})
    result = agent.review('保证有效。')
    assert events == ['cheap', 'rag', 'semantic']
    assert result['score'] == 0
    assert result['hit_count'] == 1
    assert {h['axis'] for h in result['raw_hits']} == {'efficacy_claim', 'safety_guarantee'}
    assert result['hits'][0]['original_quote'] == '保证有效'
