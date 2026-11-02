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


def db_query_violation_history(client_id: int, limit: int = 5) -> list[dict]:
    """返回机构最近完整违规审查，不把未完成/合规记为违规；非法参数报错。"""
    require_positive(client_id, "client_id")
    require_positive(limit, "limit", MAX_LIMIT)
    from backend.db.models import Audit, Script
    from backend.db.session import SessionLocal
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
    try:
        payload = json.dumps({"run_id": run_id, "sample": sample, "judge": judge,
                              "category": category}, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("judge must contain valid JSON values") from exc
    with REDTEAM_LOCK:
        REDTEAM_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REDTEAM_PATH.open("a", encoding="utf-8") as output:
            output.write(payload + "\n")
            output.flush()
            os.fsync(output.fileno())
    return {"ok": True}
