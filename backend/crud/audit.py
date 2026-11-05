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
        """读取话术快照；不存在返回 None。

        带 source_id 是批次1 路线A 的需要：判定要拿"所属素材的整篇文本"当上下文。
        这是内部快照加字段，不改任何接口响应结构。
        """
        row = self.session.get(Script, script_id)
        return None if row is None else dict(id=row.id, client_id=row.client_id,
                                             content=row.content, source_id=row.source_id)

    def audit(self, audit_id):
        """读取改写所需快照；保留所有审计轨迹。"""
        row = self.session.get(Audit, audit_id)
        if row is None:
            return None
        return dict(id=row.id, script_id=row.script_id, hits=row.hits_json or [],
                    **{key: getattr(row, key) for key in AUDIT_METADATA})

    def review_queue(self, status="pending", client_id=None, page=1, page_size=20):
        """待复核队列：按机构裁剪、按状态过滤，最近优先。

        队列只暴露"机器拿不准、需要人看 "的记录，不做二次判定，
        避免把同一个结论既当机器结果又当人工结果。
        """
        from sqlalchemy import func, select
        from backend.db.models import Audit, Script

        criteria = []
        if status:
            criteria.append(Audit.review_status == status)
        else:
            criteria.append(Audit.review_status.is_not(None))
        if client_id is not None:
            criteria.append(
                Audit.script_id.in_(select(Script.id).where(Script.client_id == client_id)))
        total = self.session.scalar(
            select(func.count(Audit.id)).where(*criteria)) or 0
        rows = self.session.scalars(
            select(Audit).where(*criteria)
            .order_by(Audit.created_at.desc(), Audit.id.desc())
            .offset((page - 1) * page_size).limit(page_size)).all()
        return rows, int(total)

    def review(self, audit_id, verdict, reviewer_id, note=None):
        """写入人工裁定；裁定一旦写下不可被另一次裁定静默覆盖。

        只允许从 pending（或未裁定）转为终态：人工投入不能被后来的点击抹掉，
        需要改判必须显式重置（本版本不做，避免留下无痕修改）。
        """
        from datetime import datetime

        from backend.core.errors import BusinessValidationError, NotFoundError

        row = self.session.get(Audit, audit_id)
        if row is None:
            raise NotFoundError("audit", audit_id)
        if row.review_status in ("confirmed", "dismissed"):
            raise BusinessValidationError(
                f"审查 {audit_id} 已由人工裁定为 {row.review_status}，不可重复裁定")
        if verdict not in ("confirmed", "dismissed"):
            raise BusinessValidationError("verdict 只能是 confirmed 或 dismissed")
        row.review_status = verdict
        row.reviewed_by = reviewer_id
        row.review_note = (note or "").strip()[:500] or None
        row.reviewed_at = datetime.now()
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(row)
        return row

    def review_stats(self, client_id=None):
        """复核统计：待办数 + 人工与机器的一致率。

        一致率的分母只算已裁定的记录：把 pending 也算进去会稀释真实一致率。
        """
        from sqlalchemy import func, select
        from backend.db.models import Audit, Script

        criteria = [Audit.review_status.is_not(None)]
        if client_id is not None:
            criteria.append(
                Audit.script_id.in_(select(Script.id).where(Script.client_id == client_id)))
        counts = dict(self.session.execute(
            select(Audit.review_status, func.count(Audit.id))
            .where(*criteria).group_by(Audit.review_status)).all())
        pending = int(counts.get("pending", 0))
        confirmed = int(counts.get("confirmed", 0))
        dismissed = int(counts.get("dismissed", 0))
        judged = confirmed + dismissed
        return {
            "pending": pending,
            "confirmed": confirmed,
            "dismissed": dismissed,
            "judged": judged,
            "agree_rate": (confirmed / judged) if judged else None,
        }

    @staticmethod
    def needs_human_review(result) -> bool:
        """判断这次审查要不要进人工复核队列。

        三类必须进：判定未完成（机器没跑完）、疑似（分级闸降级后的 soft）、
        以及分数为 1 的轻微风险。都不进的话，L3 就只是个标签。
        """
        if result.get("incomplete"):
            return True
        if result.get("score") == 1:
            return True
        return any(hit.get("downgraded") for hit in (result.get("hits") or []))

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
                    law_refs_json=result.get("law_refs", []),
                    review_status="pending" if self.needs_human_review(result) else None,
                    **metadata)
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
