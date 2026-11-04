"""D4本地边界测试，不调用付费模型。"""
import pytest


def test_redteam_migration_preview_partial_skip():
    from scripts.migrate_scripts_redteam import plan
    class Inspector:
        columns = []
        def get_columns(self, table): return self.columns
    inspector = Inspector()
    assert len(plan(inspector)) == 2
    inspector.columns = [dict(name='source')]
    assert len(plan(inspector)) == 1
    inspector.columns.append(dict(name='redteam_meta'))
    assert plan(inspector) == []



def sample_rows():
    return [dict(content=f'双眼皮咨询{a}{s}',scene='双眼皮',target_axis=a,strength=s,
                 strategy='口语场景',pattern_ref='fixture pattern '+a,expected_violation=s!='control')
            for a in ['efficacy_claim','safety_guarantee','absolute_terms','inducement']
            for s in ['low','mid','high','control']]


def test_generator_one_call_and_rejects_missing_axis():
    from backend.agents.redteam import RedTeamAgent
    import json
    class Model:
        calls = 0
        def complete(self, messages):
            self.calls += 1
            return dict(content=json.dumps({'samples':sample_rows()}),cost=0.001,
                        prompt_tokens=1,completion_tokens=1)
    model = Model()
    agent = RedTeamAgent(model,lambda:[dict(axis=a,pattern="fixture pattern "+a,law_article="广告法第16条") for a in ["efficacy_claim","safety_guarantee","absolute_terms","inducement"]])
    result = agent.generate(['双眼皮'],['efficacy_claim','safety_guarantee','absolute_terms','inducement'])
    assert len(result['samples']) == 16 and model.calls == 1
    rows = sample_rows()
    del rows[0]['target_axis']
    model.complete = lambda m:dict(content=json.dumps({'samples':rows}))
    with pytest.raises(ValueError,match='target_axis'): agent.generate(['双眼皮'],['efficacy_claim'])


def test_verdict_matrix_and_incomplete():
    from backend.agents.redteam import JudgeAgent
    assert JudgeAgent.classify(True,dict(score=0,incomplete=False)) == 'TP'
    assert JudgeAgent.classify(True,dict(score=2,incomplete=False)) == 'FN'
    assert JudgeAgent.classify(False,dict(score=1,incomplete=False)) == 'FP'
    assert JudgeAgent.classify(False,dict(score=2,incomplete=False)) == 'TN'
    assert JudgeAgent.classify(True,dict(score=-1,incomplete=True)) == 'unjudged'



def test_redteam_persistence_and_report_numbers(db):
    from backend.tools.db_tool import RedteamRepository
    from backend.db.models import Client, Script, Audit
    from sqlalchemy import select,func
    from datetime import date
    from backend.agents.redteam import AuditReportAgent
    c = Client(name='D4 fixture')
    db.add(c); db.commit()
    repo = RedteamRepository(db)
    ids = repo.save_samples('fixture_run',c.id,sample_rows(),dict(cost=0.001))
    assert len(ids) == 16
    assert db.scalar(select(func.count()).select_from(Audit)) == 0
    row = db.get(Script,ids[0])
    assert row.source == 'redteam' and row.redteam_meta['run_id']=='fixture_run'
    assert row.redteam_meta['target_axis']=='efficacy_claim'
    for i,(verdict,score) in enumerate([('TP',0),('FN',2),('FP',0),('TN',2),('unjudged',-1)]):
        repo.save_verdict(ids[i],dict(expected_violation=verdict not in ('FP','TN'),verdict=verdict,actual_axes=['efficacy_claim'] if score==0 else [],score=score))
        db.add(Audit(script_id=ids[i],score=score,hit_count=0,hits_json=[],incomplete=score==-1,cost=0.001,latency_ms=10))
    db.commit()
    gaps = repo.gaps('fixture_run')
    assert gaps['counts']['TP_axis']==1 and gaps['counts']['FN']==1
    assert gaps['counts']['FP']==1 and gaps['counts']['TN']==1
    assert gaps['counts']['unjudged']==12
    assert gaps['fn_rate']==0.5 and gaps['fp_rate']==0.5
    assert gaps['accuracy']==0.125
    report = AuditReportAgent(repo).daily(date.today())
    assert report['total']==5 and report['incomplete']==1
    assert report['compliant']==2 and report['violations']==2
    from decimal import Decimal
    assert report['cost']==Decimal('0.005000')



def test_d4_routes_authenticated(client):
    assert client.post('/api/v1/redteam/run',json=dict(client_id=1,scenes=['双眼皮'],axes=['efficacy_claim'])).status_code==401
    for path in ['/api/v1/redteam/run1/gaps','/api/v1/reports/redteam/run1','/api/v1/reports/daily?date=2026-11-04']:
        assert client.get(path).status_code==401



def test_mcp_save_updates_exact_redteam_script(db):
    from backend.db.models import Client, Script
    from backend.tools.db_tool import RedteamRepository,db_save_redteam_result,db_query_violation_history
    c=Client(name='MCP fixture');db.add(c);db.commit()
    repo=RedteamRepository(db)
    ids=repo.save_samples('mcp_run',c.id,sample_rows(),{})
    db_save_redteam_result('mcp_run',sample_rows()[0]['content'],dict(script_id=ids[0],score=2,actual_axes=[]),'FN')
    db.expire_all()
    assert db.get(Script,ids[0]).redteam_meta['verdict']=='FN'
    rows=db_query_violation_history(c.id,100,run_id='mcp_run')
    assert len(rows)==16



def test_fullchain_meter_counts_rewrite_and_embeddings_without_network():
    from backend.rag.embedding import usage_meter, record_usage
    from decimal import Decimal
    with usage_meter() as usage:
        record_usage('/chat/completions',dict(usage=dict(prompt_tokens=1000,completion_tokens=1000)),
                     dict(JUDGE_INPUT_PRICE_PER_M='0.8',JUDGE_OUTPUT_PRICE_PER_M='2.7'))
        record_usage('/embeddings',dict(usage=dict(total_tokens=1000)),dict(EMBEDDING_PRICE_PER_M='0.1'))
    assert usage['rag_rewrite']['cost']==Decimal('0.003500')
    assert usage['embedding']['cost']==Decimal('0.000100')



def test_orchestration_judges_once_per_sample_and_reports(db,client,auth_headers,monkeypatch):
    import json
    from backend.db.models import Client
    from backend.services.compliance import run_redteam
    from backend.api.v1 import ai
    c=Client(name='D4 service');db.add(c);db.commit()
    class Model:
        calls=0
        def complete(self,messages):
            self.calls+=1
            return dict(content=json.dumps({'samples':sample_rows()}),cost=0.001)
    class Auditor:
        calls=[]
        def run_audit(self,script_id,client_id):
            self.calls.append(script_id)
            return dict(score=2,incomplete=False,hits=[],audit_id=None,cost=0,latency_ms=1)
    from backend.db.models import Rule
    db.add_all([Rule(axis=a,pattern='fixture pattern '+a,law_article='广告法第16条',level='hard',detector='llm_judge') for a in ['efficacy_claim','safety_guarantee','absolute_terms','inducement']]);db.commit()
    model,judge=Model(),Auditor()
    result=run_redteam(db,c.id,['双眼皮'],['efficacy_claim','safety_guarantee','absolute_terms','inducement'],model,judge)
    assert model.calls==1 and len(judge.calls)==16
    from backend.tools.db_tool import RedteamRepository
    from backend.agents.redteam import AuditReportAgent
    repo=RedteamRepository(db)
    report=AuditReportAgent(repo).redteam(result['run_id'])
    assert report['counts']==dict(TP_axis=0,TP_other=0,FN=12,FP=0,TN=4,unjudged=0)
    assert report['accuracy']==0.25
    monkeypatch.setattr(ai,'redteam_operations',lambda session:dict(repository=repo,report=AuditReportAgent(repo)))
    response=client.get('/api/v1/reports/redteam/'+result['run_id'],headers=auth_headers)
    assert response.status_code==200 and response.json()['data']['generated']==16


def test_report_model_cannot_add_facts():
    from backend.agents.redteam import AuditReportAgent
    class Repo:
        # 签名与仓储层保持一致：多出的 client_id 用于商家端只看自己机构
        def daily(self,day,client_id=None): return dict(total=1,incomplete=0)
    class Model:
        def complete(self,messages): return dict(content='{"template_id":"daily","extra":"99%合规"}')
    with pytest.raises(ValueError,match='new facts'): AuditReportAgent(Repo(),Model()).daily(None)
