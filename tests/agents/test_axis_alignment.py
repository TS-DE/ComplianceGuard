"""生成规则引用和目标轴矩阵契约，全部本地stub。"""
import json
import pytest
from backend.agents.redteam import RedTeamAgent,JudgeAgent

PATTERN='制造容貌焦虑，与低能贫穷关联'


def rules():
    return [dict(axis='inducement',pattern=PATTERN,law_article='医美指南第五条(一)',enabled=True)]


def test_prompt_uses_rules_and_invalid_pattern_excluded():
    class Model:
        def complete(self,messages):
            assert PATTERN in messages[1]['content']
            rows=[dict(axis='inducement',pattern_ref=PATTERN if s!='mid' else '促销紧迫',
                strength=s,text='话术'+s,expected_violation=s!='control',strategy='场景',scene='双眼皮')
                for s in ['low','mid','high','control']]
            return dict(content=json.dumps({'samples':rows}),cost=0)
    result=RedTeamAgent(Model(),rules).generate(['双眼皮'],['inducement'])
    assert len(result['samples'])==3
    assert result['invalid_samples'][0]['status']=='invalid_axis_ref'


def test_missing_axis_rejected_before_model():
    with pytest.raises(ValueError,match='enabled rule.*inducement'):
        RedTeamAgent(object(),lambda:[]).generate(['双眼皮'],['inducement'])


def test_target_axis_matrix():
    assert JudgeAgent.classify(True,dict(score=0,incomplete=False),'inducement',['inducement'])=='TP_axis'
    assert JudgeAgent.classify(True,dict(score=0,incomplete=False),'inducement',['efficacy_claim'])=='TP_other'
    assert JudgeAgent.classify(True,dict(score=2,incomplete=False),'inducement',[])=='FN'
    assert JudgeAgent.classify(False,dict(score=0,incomplete=False),'inducement',[])=='FP'
    assert JudgeAgent.classify(False,dict(score=2,incomplete=False),'inducement',[])=='TN'



def test_two_rates_and_invalid_exclusion():
    from backend.tools.db_tool import RedteamRepository
    rows=[]
    for i,(expected,score,actual) in enumerate([(True,0,['inducement']),(True,0,['efficacy_claim']),(True,2,[]),(False,0,[]),(False,2,[])]):
        rows.append(dict(id=i,content='fixture',meta=dict(target_axis='inducement',expected_violation=expected,score=score,actual_axes=actual,verdict='old')))
    rows.append(dict(id=99,meta=dict(label_invalid=True)))
    report=RedteamRepository.summarize(rows)
    assert report['counts']==dict(TP_axis=1,TP_other=1,FN=1,FP=1,TN=1,unjudged=0)
    assert report['fn_rate']==1/3
    assert report['axis_fn_rate']==2/3
    assert report['generated']==5
