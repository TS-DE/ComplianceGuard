"""D3 契约回归，仅使用本地可控检测器。"""
from backend.agents.base import Detector
from backend.agents.compliance import ComplianceAuditAgent

SRC = '这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效'


class Echo(Detector):
    def detect(self, text, rule):
        return [dict(quote=text, pattern=rule.pattern, law_article=rule.law_article)]


def test_quotes_are_original_after_nfkc():
    for source in [SRC, 'Ａ；， " "、（保证）', 'Ａ\u200b  Ｂ']:
        rule = dict(axis='efficacy_claim', pattern='功效', law_article='广告法第16条', detector='echo')
        result = ComplianceAuditAgent(lambda: [rule], lambda q: [dict(code='广告法第16条')],
                                     None, {'echo': Echo()}).review(source)
        assert result['hits']
        assert all(source.find(h['quote']) >= 0 for h in result['hits'])


class Candidate(Detector):
    def __init__(self, pattern, law):
        self.pattern, self.law = pattern, law

    def detect(self, text, rule):
        return [dict(quote=text, pattern=self.pattern, law_article=self.law)]


def check_axis(pattern, declared, cited, known):
    rule = dict(axis='safety_guarantee', pattern='安全', law_article=declared, detector='probe')
    return ComplianceAuditAgent(lambda: [rule], lambda q: [dict(code=cited)], None,
                               {'probe': Candidate(pattern, cited)}, known_docs=known).review('非常安全')


def test_wrong_axis_pattern_rejected():
    result = check_axis('功效', '广告法第16条', '广告法第16条', {'广告法'})
    assert not result['hits']
    assert result['traces'][0]['status'] == 'cross_axis_rejected'


def test_article_level_membership_passes():
    result = check_axis('安全', '医疗广告管理办法第7条(六)', '医疗广告管理办法第7条', {'医疗广告管理办法'})
    assert result['hits']


def test_missing_document_warns_only():
    result = check_axis('安全', '缺失法规第7条', '广告法第16条', {'广告法'})
    assert result['hits']
    assert any(t['status'] == 'law_ref_missing' for t in result['traces'])


def test_other_axis_law_rejected():
    result = check_axis('安全', '广告法第16条', '广告法第9条', {'广告法'})
    assert not result['hits']
    assert result['traces'][0]['status'] == 'cross_axis_rejected'



def test_concurrent_matches_serial_and_retrieves_once(caplog):
    import json
    from time import sleep
    from backend.agents.base import ChatModel

    class Model(ChatModel):
        def complete(self, messages):
            axis = json.loads(messages[1]['content'])['axis']
            sleep(0.01)
            return dict(content=json.dumps({'hits': [dict(quote='非常安全',
                law_article='广告法第16条', reason=axis)]}), model='stub',
                prompt_tokens=3, completion_tokens=2, cost=0.001)

    rules = [dict(axis=str(i), pattern='安全', law_article='广告法第16条') for i in range(8)]
    results = []
    for workers in (1, 4):
        calls = []
        def search(query):
            calls.append(query)
            return [dict(code='广告法第16条')]
        agent = ComplianceAuditAgent(lambda: rules, search, Model(), workers=workers)
        result = agent.review('非常安全')
        assert len(calls) == 1
        assert result['prompt_tokens'] == 24
        assert set(result['timings_ms']) >= {'normalize', 'rules', 'retrieve', 'detect', 'aggregate'}
        results.append(result['hits'])
    assert results[0] == results[1]



def test_sentence_claims_keep_raw_axis_evidence():
    rules = [dict(axis=axis, pattern='安全', law_article='广告法第16条', detector='echo')
             for axis in ('efficacy_claim', 'safety_guarantee')]
    result = ComplianceAuditAgent(lambda: rules, lambda q: [dict(code='广告法第16条')],
                                 None, {'echo': Echo()}).review('非常安全')
    assert result['hit_count'] == len(result['hits']) == 1
    assert result['hits'][0]['axes'] == ['efficacy_claim', 'safety_guarantee']
    assert len(result['raw_hits']) == 2



def test_item_metadata_rejects_wrong_axis_and_preserves_provenance():
    rule = dict(axis='before_after', pattern='患者对比', law_article='医美指南第五条(五)', detector='echo')
    chunk = dict(code='医疗美容广告执法指南第5条', item_no='第五条(四)', chunk_id='trusted:5:4')
    detector = Candidate('患者对比', chunk['code'])
    result = ComplianceAuditAgent(lambda: [rule], lambda q:[chunk], None, {'echo':detector}).review('保证有效')
    assert not result['hits']
    assert result['traces'][0]['status'] == 'item_mismatch'
    assert result['traces'][0]['ref'] == '医疗美容广告执法指南.5.4'
