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


# ---------------------------------------------------------------- 同句多轴并存（B 阶段）
def _both_axes():
    """一句里同时有疗效保证和安全性保证，两轴各自独立命中。"""
    return [dict(axis='efficacy_claim',severity='hard',sentence_id=0,quote='保证白三个度',law_article='广告法第16条'),
            dict(axis='safety_guarantee',severity='hard',sentence_id=0,quote='零风险，绝对安全',law_article='广告法第16条')]


def test_same_sentence_multi_axis_survives_aggregation():
    """聚合成一条 claim 时两轴都必须留痕，主轴字段不等于"只命中一轴"。

    上一轮的 A/B 脚本按 claim['axis'] 统计硬命中轴，把"同句多轴聚合成一条显示"
    读成了漏判，量出 3 条假"轴漂移"（产品侧 JudgeAgent 一直读的是 axes 全集）。
    这个测试钉住正确的读取方式，防止那种口径再被当成真实结论。
    """
    from backend.agents.compliance import aggregate_claims
    claims=aggregate_claims([dict(h) for h in _both_axes()])
    assert len(claims)==1 and claims[0]['axes']==['efficacy_claim','safety_guarantee']
    assert [e['axis'] for e in claims[0]['evidence']]==['efficacy_claim','safety_guarantee']
    assert claims[0]['axis']=='efficacy_claim'  # 主轴只是首条，不能拿它当全集


def test_multi_axis_coexistence_does_not_inflate_score():
    """允许并存不得让分数虚增：一句两轴与一句一轴同为 0，靠句数而不是轴数累加。"""
    from backend.agents.compliance import _score, aggregate_claims
    single=aggregate_claims([dict(axis='efficacy_claim',severity='hard',sentence_id=0,quote='保证白三个度')])
    both=aggregate_claims([dict(h) for h in _both_axes()])
    assert len(both)==len(single)==1
    assert _score(both)==_score(single)==0


def test_soft_axis_next_to_hard_axis_stays_hard_regardless_of_order():
    """并存时严重度按轴各自保留，且结论不得依赖模型返回顺序。

    旧实现把首条命中的 downgraded 复制成整句的属性：首条恰好是被降级的疗效提示时，
    同句里真实存在的硬安全性违规会被算成"仅提示"（0 变 1）。这是漏放，不是显示问题。
    """
    from backend.agents.compliance import _score, aggregate_claims
    soft=dict(axis='efficacy_claim',severity='soft',sentence_id=0,quote='可能需要三个月',downgraded=True)
    hard=dict(axis='safety_guarantee',severity='hard',sentence_id=0,quote='零风险')
    for order in ([soft,hard],[hard,soft]):
        claims=aggregate_claims([dict(h) for h in order])
        assert claims[0]['severity']=='hard', order
        assert claims[0]['downgraded'] is False, order
        assert _score(claims)==0, order
    only_soft=aggregate_claims([dict(soft)])
    assert only_soft[0]['downgraded'] is True and _score(only_soft)==1
