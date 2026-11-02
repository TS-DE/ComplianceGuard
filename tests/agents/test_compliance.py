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


def test_fabricated_quote_discarded():
    r = audit('正常介绍', [dict(quote='编造', law_article='广告法第9条', reason='x')])
    assert r['hits'] == []
    assert r['traces'][0]['status'] == 'invalid_quote'


def test_unretrieved_law_discarded():
    r = audit('最佳', [dict(quote='最佳', law_article='广告法第999条', reason='x')])
    assert r['hits'] == []
    assert r['traces'][0]['status'] == 'invalid_law_ref'


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
             dict(axis='safety_guarantee', detector='keyword')]
    def search(query):
        events.append('rag')
        return [dict(code='广告法第16条', text='不得保证疗效')]
    agent = ComplianceAuditAgent(lambda: rules, search, None,
        detectors={'keyword': Probe('cheap'), 'llm_judge': Probe('semantic')})
    result = agent.review('保证有效。')
    assert events == ['cheap', 'rag', 'rag', 'semantic']
    assert result['score'] == 0
    assert result['hit_count'] == 1
    assert {h['axis'] for h in result['hits']} == {'efficacy_claim', 'safety_guarantee'}
    assert result['hits'][0]['original_quote'] == '保证有效'
