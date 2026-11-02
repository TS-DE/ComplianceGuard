"""audits 表读写：纯数据库操作。"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.crud.base import paginate
from backend.db.models import Audit
from backend.db.models import Script


def get(db: Session, audit_id: int) -> Audit | None:
    """按主键取审查记录。"""
    return db.get(Audit, audit_id)


def list_paged(
    db: Session,
    page: int,
    page_size: int,
    client_id: int | None = None,
) -> tuple[list[Audit], int]:
    """分页查询；client_id 过滤需 join scripts（audits 本身没有该列）。"""
    stmt = select(Audit).order_by(Audit.id.desc())
    if client_id is not None:
        stmt = stmt.join(Script, Audit.script_id == Script.id).where(
            Script.client_id == client_id
        )
    return paginate(db, stmt, page, page_size)


def create(db: Session, data: dict[str, Any]) -> Audit:
    """插入并提交。"""
    obj = Audit(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, obj: Audit, data: dict[str, Any]) -> Audit:
    """按传入字段更新并提交。"""
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, obj: Audit) -> None:
    """删除并提交。"""
    db.delete(obj)
    db.commit()


def count_by_script(db: Session, script_id: int) -> int:
    """统计某话术的审查记录数（删除话术前的引用检查）。"""
    stmt = select(func.count()).select_from(Audit).where(Audit.script_id == script_id)
    return int(db.execute(stmt).scalar_one())
