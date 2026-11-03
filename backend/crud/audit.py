"""审查持久化边界：规则快照、资源读取和原子审计写入。"""
from dataclasses import fields
from decimal import Decimal

from sqlalchemy import select

from backend.agents.base import Rule as AgentRule
from backend.core.config import SCORE_INCOMPLETE, ScriptStatus
from backend.core.constants import add_cost
from backend.db.models import Audit, Client, Rule, Script

AUDIT_METADATA = ("score", "hit_count", "model", "prompt_tokens", "completion_tokens",
                  "cost", "latency_ms", "incomplete")


class AuditRepository:
    """返回字典而不是 ORM 对象，禁止业务层穿透数据库关系。"""

    def __init__(self, session):
        """注入当前事务 Session；Session 生命周期由调用方管理。"""
        self.session = session

    def load_rules(self):
        """读取启用规则并剥离非 AgentRule 字段；失败向上抛出。"""
        names = {field.name for field in fields(AgentRule)}
        rows = self.session.scalars(select(Rule).where(Rule.enabled.is_(True)).order_by(Rule.id))
        return [{name: getattr(row, name) for name in names if hasattr(row, name)} for row in rows]

    def client(self, client_id):
        """机构是否存在；不暴露 ORM。"""
        return self.session.get(Client, client_id) is not None

    def script(self, script_id):
        """读取话术快照；不存在返回 None。"""
        row = self.session.get(Script, script_id)
        return None if row is None else dict(id=row.id, client_id=row.client_id, content=row.content)

    def audit(self, audit_id):
        """读取改写所需快照；保留所有审计轨迹。"""
        row = self.session.get(Audit, audit_id)
        if row is None:
            return None
        return dict(id=row.id, script_id=row.script_id, hits=row.hits_json or [],
                    **{key: getattr(row, key) for key in AUDIT_METADATA})

    def save(self, script_id, result):
        """审计元数据与话术状态同一事务提交；错误回滚。"""
        hits = [dict(hit, status="active") for hit in result["hits"]]
        hits.extend(dict(hit, status="raw") for hit in result.get("raw_hits", []))
        hits.extend(dict(trace, status=trace.get("status", "trace")) for trace in result.get("traces", []))
        hits.append(dict(status="call_metadata",llm_calls=result.get("llm_calls",[])))
        metadata = {key: result[key] for key in AUDIT_METADATA}
        if metadata['incomplete']:
            metadata['score'] = SCORE_INCOMPLETE
        row = Audit(script_id=script_id, hits_json=hits,
                    law_refs_json=result.get("law_refs", []), **metadata)
        try:
            self.session.add(row)
            self.session.get(Script, script_id).status = ScriptStatus.AUDITED
            self.session.commit()
            self.session.refresh(row)
        except Exception:
            self.session.rollback()
            raise
        return row.id

    def update_latency(self, audit_id, latency_ms):
        """回填首次落库完成后的总耗时；失败回滚并抛错。"""
        try:
            self.session.get(Audit, audit_id).latency_ms = latency_ms
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def update_rewrite(self, audit_id, result):
        """保存改写状态并累计实际调用成本；保留原审查分数。"""
        row = self.session.get(Audit, audit_id)
        try:
            row.rewritten_text = result.get("rewritten_text")
            row.rewrite_passed = result["rewrite_passed"]
            row.cost = add_cost(row.cost, result.get("cost"))
            for key in ("prompt_tokens", "completion_tokens", "latency_ms"):
                setattr(row, key, getattr(row, key) + result.get(key, 0))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
