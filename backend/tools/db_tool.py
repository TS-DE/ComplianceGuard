"""MCP 本地数据库工具；查询只读，红队样本仅写内部 JSONL。"""

import json
import os
from pathlib import Path
from threading import Lock

from sqlalchemy import MetaData, Table, func, select

MAX_LIMIT = 100
SCENE_SAMPLE_LIMIT = 3
REDTEAM_PATH = Path(__file__).resolve().parents[2] / "data" / "redteam" / "results.jsonl"
OPTIONAL_RULE_COLUMNS = ("detector", "exemptions")
REDTEAM_LOCK = Lock()


def require_text(value: str, name: str) -> None:
    """校验非空字符串参数；不修改原文，非法值抛 ValueError。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def require_positive(value: int, name: str, maximum: int | None = None) -> None:
    """校验正整数及可选上限；拒绝布尔值，非法值抛 ValueError。"""
    if type(value) is not int or value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be a positive integer" +
                         (f" <= {maximum}" if maximum is not None else ""))


def db_query_rules(axis: str | None = None) -> list[dict]:
    """只读反射启用规则；返回可用字段及缺列状态，数据库异常上抛。"""
    if axis is not None:
        require_text(axis, "axis")
    from backend.db.session import SessionLocal
    with SessionLocal() as session:
        rules = Table("rules", MetaData(), autoload_with=session.connection())
        missing = [name for name in OPTIONAL_RULE_COLUMNS if name not in rules.c]
        statement = select(rules).where(rules.c.enabled.is_(True)).order_by(rules.c.id)
        if axis is not None:
            statement = statement.where(rules.c.axis == axis)
        result = []
        for row in session.execute(statement).mappings():
            item = dict(row)
            for name in OPTIONAL_RULE_COLUMNS:
                item.setdefault(name, None)
            item.update(schema_status="missing_columns" if missing else "complete",
                        missing_columns=missing)
            result.append(item)
        return result


def db_query_violation_history(client_id: int, limit: int = 5, run_id: str | None = None) -> list[dict]:
    """返回机构最近完整违规审查，不把未完成/合规记为违规；非法参数报错。"""
    require_positive(client_id, "client_id")
    require_positive(limit, "limit", MAX_LIMIT)
    from backend.db.models import Audit, Script
    from backend.db.session import SessionLocal
    if run_id is not None:
        require_text(run_id, 'run_id')
        with SessionLocal() as session:
            return [row for row in RedteamRepository(session).samples(run_id) if row['client_id']==client_id][:limit]
    statement = (select(Audit.script_id, Audit.score, Audit.hits_json, Audit.created_at)
                 .join(Script, Audit.script_id == Script.id)
                 .where(Script.client_id == client_id, Audit.score.in_((0, 1)),
                        Audit.incomplete.is_(False))
                 .order_by(Audit.created_at.desc(), Audit.id.desc()).limit(limit))
    with SessionLocal() as session:
        return [{"script_id": row.script_id, "score": row.score,
                 "hits": row.hits_json or [], "created_at": row.created_at.isoformat()}
                for row in session.execute(statement)]


def db_query_scenes() -> list[dict]:
    """读取非空场景及最多三个去重原文示例；数据库异常上抛。"""
    from backend.db.models import Script
    from backend.db.session import SessionLocal
    with SessionLocal() as session:
        scenes = session.scalars(select(Script.scene).where(
            Script.scene.is_not(None), Script.scene != "").distinct().order_by(Script.scene))
        result = []
        for scene in scenes:
            if not scene.strip():
                continue
            samples = session.scalars(select(Script.content).where(Script.scene == scene)
                                      .group_by(Script.content).order_by(func.min(Script.id))
                                      .limit(SCENE_SAMPLE_LIMIT)).all()
            result.append({"scene": scene, "sample_scripts": list(samples)})
        return result


def db_save_redteam_result(run_id: str, sample: str, judge: dict, category: str) -> dict:
    """内部 JSONL 持久化；输入不合法或写盘失败抛错，成功落盘才返回 ok。"""
    for name, value in (("run_id", run_id), ("sample", sample), ("category", category)):
        require_text(value, name)
    if not isinstance(judge, dict):
        raise ValueError("judge must be a JSON object")
    if category not in ('TP','FN','FP','TN','unjudged'):
        raise ValueError('invalid verdict')
    from backend.db.session import SessionLocal
    with SessionLocal() as session:
        repo=RedteamRepository(session)
        rows=[r for r in repo.samples(run_id) if r['content']==sample and
              (judge.get('script_id') is None or judge['script_id']==r['id'])]
        if len(rows)!=1: raise ValueError('sample must identify exactly one redteam script')
        repo.save_verdict(rows[0]['id'],dict(judge,verdict=category))
    return {'ok':True}



class RedteamRepository:
    """红队脚本、判定meta与只读报告的基础设施适配。"""
    def __init__(self, session):
        self.db = session

    def save_samples(self, run_id, client_id, rows, usage):
        """一次事务写整个生成矩阵，生成失败不写半批。"""
        from backend.db.models import Script, Client
        from backend.core.errors import NotFoundError
        if self.db.get(Client,client_id) is None: raise NotFoundError('client',client_id)
        objects = []
        for index,row in enumerate(rows):
            meta = {k:row[k] for k in ('target_axis','strength','strategy','expected_violation')}
            meta.update(run_id=run_id)
            if index == 0:
                meta['generation_usage'] = json.loads(json.dumps(usage,default=str))
            objects.append(Script(client_id=client_id,scene=row['scene'],content=row['content'],
                                  source='redteam',redteam_meta=meta))
        self.db.add_all(objects)
        self.db.commit()
        return [obj.id for obj in objects]

    def samples(self, run_id):
        """按run_id返回原文及元数据快照，不暴露ORM关系。"""
        from backend.db.models import Script
        rows = self.db.scalars(select(Script).where(Script.source=='redteam',
            Script.redteam_meta['run_id'].as_string()==run_id).order_by(Script.id)).all()
        return [dict(id=r.id,client_id=r.client_id,scene=r.scene,content=r.content,meta=r.redteam_meta) for r in rows]

    def save_verdict(self, script_id, result):
        """追加判定快照，保留生成目标与用量；JSON赋新对象触发ORM跟踪。"""
        from backend.db.models import Script
        from backend.core.errors import NotFoundError
        row = self.db.get(Script,script_id)
        if row is None or row.source!='redteam': raise NotFoundError('redteam_script',script_id)
        row.redteam_meta = dict(row.redteam_meta,**json.loads(json.dumps(result,default=str)))
        self.db.commit()

    def gaps(self, run_id):
        """从已存meta复算矩阵，空分母为None，未判定独立列。"""
        from collections import Counter
        from backend.core.errors import NotFoundError
        rows = self.samples(run_id)
        if not rows: raise NotFoundError('redteam_run',run_id)
        counts = Counter(row['meta'].get('verdict','unjudged') for row in rows)
        axes = {}
        for row in rows:
            m=row['meta']; bucket=axes.setdefault(m['target_axis'],dict(expected_violations=0,TP=0,FN=0,FP=0,TN=0,unjudged=0))
            bucket['expected_violations'] += int(m['expected_violation'])
            bucket[m.get('verdict','unjudged')] += 1
        for bucket in axes.values():
            denominator=bucket['TP']+bucket['FN']
            bucket['fn_rate']=bucket['FN']/denominator if denominator else None
        denominator=counts['TP']+counts['FN']; negative=counts['FP']+counts['TN']
        return dict(costs=self.run_costs(run_id),run_id=run_id,generated=len(rows),counts={k:counts[k] for k in ('TP','FN','FP','TN','unjudged')},
                    fn_rate=counts['FN']/denominator if denominator else None,
                    fp_rate=counts['FP']/negative if negative else None,
                    accuracy=(counts['TP']+counts['TN'])/len(rows),by_axis=axes,
                    FN=[r for r in rows if r['meta'].get('verdict')=='FN'],
                    FP=[r for r in rows if r['meta'].get('verdict')=='FP'],samples=rows)

    def run_costs(self, run_id):
        """从已存meta汇总三项费用及生成成本，未知项传播NULL。"""
        from decimal import Decimal
        from backend.core.constants import add_cost
        totals=dict(judge_cost=Decimal('0'),rewrite_cost=Decimal('0'),embedding_cost=Decimal('0'))
        tokens=dict(judge_tokens=0,rewrite_tokens=0,embedding_tokens=0)
        generation=Decimal('0')
        latency=0
        for row in self.samples(run_id):
            meta=row['meta']; breakdown=meta.get('cost_breakdown')
            if 'generation_usage' in meta:
                value=meta['generation_usage'].get('cost')
                generation=add_cost(generation,value)
            if not breakdown:
                if meta.get('verdict'): totals={key:None for key in totals}
                continue
            for label,kind in [('judge','a1'),('rewrite','rag_rewrite'),('embedding','embedding')]:
                usage=breakdown.get(kind,{})
                totals[label+'_cost']=add_cost(totals[label+'_cost'],usage.get('cost'))
                tokens[label+'_tokens']+=int(usage.get('prompt_tokens',0))+int(usage.get('completion_tokens',0))
            latency+=meta.get('latency_ms') or 0
        total=add_cost(add_cost(totals['judge_cost'],totals['rewrite_cost']),totals['embedding_cost'])
        ratio=tokens['embedding_tokens']/tokens['judge_tokens'] if tokens['judge_tokens'] else None
        return dict(totals,**tokens,total_cost=total,generation_cost=generation,
                    run_total_cost=add_cost(total,generation),latency_ms=latency,embedding_token_ratio=ratio,
                    cost_note='全链路估算，非供应商账单；embedding未计价，token占比不等于费用占比')

    def daily(self, day):
        """SQL复算审计总数、完整分数分布、均时、费用；NULL费用独立计数。"""
        from datetime import datetime, time, timedelta
        from sqlalchemy import case
        from backend.db.models import Audit
        start=datetime.combine(day,time.min)
        criteria=(Audit.created_at>=start,Audit.created_at<start+timedelta(days=1))
        complete=(Audit.incomplete.is_(False) & Audit.score.in_((0,1,2)))
        statement=select(func.count(Audit.id).label('total'),
            func.sum(case((~complete,1),else_=0)).label('incomplete'),
            func.sum(case((complete & (Audit.score==2),1),else_=0)).label('compliant'),
            func.sum(case((complete & Audit.score.in_((0,1)),1),else_=0)).label('violations'),
            func.avg(Audit.latency_ms).label('average_latency_ms'),func.sum(Audit.cost).label('cost'),
            func.sum(case((Audit.cost.is_(None),1),else_=0)).label('unpriced')).where(*criteria)
        data=dict(self.db.execute(statement).mappings().one())
        for key in ('total','incomplete','compliant','violations','unpriced'): data[key]=int(data[key] or 0)
        axes={}
        for hits in self.db.scalars(select(Audit.hits_json).where(*criteria,complete)):
            unique={a for h in hits or [] if h.get('status','active')=='active' for a in h.get('axes',[h.get('axis')]) if a}
            for axis in unique: axes[axis]=axes.get(axis,0)+1
        data['known_cost_subtotal']=data['cost']
        if data['unpriced']: data['cost']=None
        judged=data['total']-data['incomplete']
        return dict(data,date=day.isoformat(),by_axis=axes,
                    violation_rate=data['violations']/judged if judged else None)
