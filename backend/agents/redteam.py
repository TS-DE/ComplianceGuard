"""A3递进生成、A4独立调用A1、A5只解释已有数字；均依赖可注入边界。"""
import json
import logging
from backend.core.config import DISCLAIMER_TEXT


class RedTeamAgent:
    """一次调用全部目标轴的三档违规样本及各一条真合规对照。"""
    def __init__(self, model, rules_loader=None):
        self.model = model
        if rules_loader is None:
            from backend.tools.db_tool import db_query_rules
            rules_loader=db_query_rules
        self.rules_loader=rules_loader

    def generate(self, scenes, axes):
        """返回已强校验矩阵及真实生成用量；缺字段拒绝整个批次。"""
        definitions={row["axis"]:row for row in self.rules_loader() if row.get("enabled",True)}
        for axis in axes:
            if axis not in definitions: raise ValueError(f"missing enabled rule for {axis}")
        response = self.model.complete([
            dict(role='system',content='仅用于内部广告法红队测试，不生成涉政涉黄涉暴内容。'
                 '像真人医美销售口语，包含场景和修饰，不堆违禁词。对每轴每场景生成low/mid/high三级递进，'
                 'low轻微越界、mid明确暗示、high显式承诺，这三档expected_violation均为true。'
                 '另每轴每场景一条control，真正合规、不含效果安全承诺，expected_violation=false。'
                 '返回JSON {"samples":[{"content":"话术","scene":"场景","axis":"轴","pattern_ref":"当前轴pattern逐字复制",'
                 '"strength":"low|mid|high|control","strategy":"策略","expected_violation":true}]}。'),
            dict(role='user',content=json.dumps(dict(scenes=scenes,axes=[{k:definitions[a][k] for k in ("axis","pattern","law_article")} for a in axes]),ensure_ascii=False))])
        rows = json.loads(response['content']).get('samples')
        required = {'content','scene','target_axis','strength','strategy','expected_violation'}
        if not isinstance(rows,list): raise ValueError('samples must be a list')
        found = set()
        invalid=[]
        for row in rows:
            if isinstance(row,dict):
                row=dict(row,target_axis=row.get('axis',row.get('target_axis')),content=row.get('text',row.get('content')))
            if not isinstance(row,dict) or required-row.keys():
                logging.getLogger(__name__).warning('redteam_invalid_sample: missing required fields')
                raise ValueError('sample requires target_axis and complete metadata')
            if not row['target_axis']: raise ValueError('missing target_axis')
            key = (row['scene'],row['target_axis'],row['strength'])
            if key in found or row['scene'] not in scenes or row['target_axis'] not in axes:
                raise ValueError('duplicate or unexpected sample axis/scene')
            if row['strength'] not in ('low','mid','high','control') or type(row['expected_violation']) is not bool:
                raise ValueError('invalid strength/expected_violation')
            if row['expected_violation'] != (row['strength'] != 'control'):
                raise ValueError('expected_violation disagrees with control group')
            if any(not isinstance(row[k],str) or not row[k].strip() for k in ('content','scene','strategy')):
                raise ValueError('sample text must be nonempty')
            found.add(key)
            if row.get("pattern_ref") != definitions[row["target_axis"]]["pattern"]:
                invalid.append(dict(row,status="invalid_axis_ref"))
        expected = {(s,a,t) for s in scenes for a in axes for t in ('low','mid','high','control')}
        if found != expected: raise ValueError('incomplete sample matrix')
        return dict(samples=[dict(row,target_axis=row.get("axis",row.get("target_axis")),content=row.get("text",row.get("content"))) for row in rows if row.get("pattern_ref")==definitions[row.get("axis",row.get("target_axis"))]["pattern"]],invalid_samples=invalid,usage={k:response.get(k) for k in ('model','prompt_tokens','completion_tokens','cost')},
                    llm_calls=list(self.model.calls) if isinstance(getattr(self.model,'calls',None),list) else [])


class JudgeAgent:
    """不复制判定逻辑，只复用注入的A1并分类。"""
    def __init__(self, auditor):
        self.auditor = auditor

    @staticmethod
    def classify(expected, result, target_axis=None, actual_axes=None):
        """未完成单列；完整结果构成TP/FN/FP/TN矩阵。"""
        if result.get('incomplete') or result.get('score') not in (0,1,2): return 'unjudged'
        if not expected: return 'FP' if result['score']<2 else 'TN'
        if result['score']==2: return 'FN'
        if target_axis is None: return 'TP'  # 兼容旧调用，正式裁判必须传目标轴
        return 'TP_axis' if target_axis in (actual_axes or []) else 'TP_other'

    def judge(self, sample):
        """每样本调用A1一次，异常如实留为未判定，不重跑。"""
        try:
            result = self.auditor.run_audit(sample['id'],sample['client_id'])
        except Exception as exc:
            return dict(verdict='unjudged',actual_axes=[],error=type(exc).__name__,score=-1)
        axes = sorted({a for h in result.get('hits',[]) for a in h.get('axes',[h.get('axis')]) if a})
        return dict(verdict=self.classify(sample['meta']['expected_violation'],result,sample['meta']['target_axis'],axes),actual_axes=axes,
                    score=result['score'],audit_id=result.get('audit_id'),cost=result.get('cost'),
                    latency_ms=result.get('latency_ms'),cost_breakdown=result.get('cost_breakdown'),
                    timings_ms=result.get('timings_ms'),llm_calls=list(result.get('llm_calls',[])))


class AuditReportAgent:
    """默认零模型成本；统计值只来自仓储查询，模型不负责算数。"""
    def __init__(self, repository, model=None):
        self.repository = repository
        self.model = model

    def daily(self, day, client_id=None):
        """返回SQL聚合数值及固定模板说明；client_id 用于商家端只看自己的数。"""
        data = self.repository.daily(day, client_id)
        summary=f"今日审查{data['total']}条，未完成{data['incomplete']}条。"
        if self.model is not None:
            summary=self._safe_narrative(summary)
        return dict(data,summary=summary,
                    disclaimer=DISCLAIMER_TEXT)

    def redteam(self, run_id):
        """返回矩阵和显式公式，未判定不混入任意矩阵格。"""
        data = self.repository.gaps(run_id)
        return dict(data,notice=f"样本量{data['generated']}，仅作内部对比，不具统计代表性",
                    formulas=dict(fn_rate='FN/(TP+FN)',fp_rate='FP/(FP+TN)',axis_fn_rate='(FN+TP_other)/(TP_axis+TP_other+FN)',accuracy='(TP_axis+TP_other+TN)/generated'),
                    disclaimer=DISCLAIMER_TEXT)


    def _safe_narrative(self, summary):
        """可选模型只能选已有模板；任何新增文本/数字均拒绝，不污染统计。"""
        response=self.model.complete([dict(role='system',content='仅返回JSON {"template_id":"daily"}，不得添加字段或数字。'),
                                      dict(role='user',content=json.dumps({'daily':summary},ensure_ascii=False))])
        if json.loads(response['content']) != {'template_id':'daily'}:
            raise ValueError('report attempted new facts')
        return summary
