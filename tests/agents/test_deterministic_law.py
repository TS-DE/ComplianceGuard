"""确定性规则法源不受RAG召回否决，LLM仍严格。"""
from backend.agents.compliance import ComplianceAuditAgent
from backend.agents.base import Detector


def review(refs,detector='regex',law='广告法第9条(三)',known=None,registry=None):
    rule=dict(axis='absolute_terms',pattern='绝对化',law_article=law,detector=detector)
    return ComplianceAuditAgent(lambda:[rule],lambda q:refs,None,registry,known_docs=known).review('最好的机构')


def test_regex_survives_missing_retrieved_law():
    result=review([dict(code='广告法第16条')])
    assert len(result['hits'])==1
    assert result['hits'][0]['law_from_rule_table']==1
    assert result['hits'][0]['ref']=='广告法.9.3'


def test_llm_unretrieved_law_still_rejected():
    class Fake(Detector):
        def detect(self,text,rule): return [dict(quote='最好',law_article='广告法第9条')]
    result=review([dict(code='广告法第16条')],detector='llm_judge',registry={'llm_judge':Fake()})
    assert result['hits']==[]
    assert result['traces'][0]['status']=='invalid_law_ref'


def test_regex_binds_matching_item_chunk():
    result=review([dict(code='广告法第9条',item_no='第九条(三)',chunk_id='law:9:3')])
    assert result['hits'][0]['chunk_id']=='law:9:3'
    assert result['hits'][0]['ref']=='广告法.9.3'


def test_missing_document_warns_but_keeps_deterministic_hit():
    result=review([],law='未知法第9条(三)',known={'广告法'})
    assert result['hits']
    assert any(t['status']=='law_ref_missing' for t in result['traces'])


def test_pattern_mismatch_still_rejected():
    class Fake(Detector):
        def detect(self,text,rule): return [dict(quote='最好',law_article=rule.law_article,pattern='其他轴')]
    result=review([],detector='keyword',registry={'keyword':Fake()})
    assert not result['hits']
    assert any(t['status']=='cross_axis_rejected' for t in result['traces'])
