"""scripts 表读写：纯数据库操作。"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.crud.base import paginate
from backend.db.models import Script


def get(db: Session, script_id: int) -> Script | None:
    """按主键取话术。"""
    return db.get(Script, script_id)


def list_paged(
    db: Session, page: int, page_size: int, client_id: int | None = None
) -> tuple[list[Script], int]:
    """分页查询，可选按 client_id 过滤。"""
    stmt = select(Script).order_by(Script.id.desc())
    if client_id is not None:
        stmt = stmt.where(Script.client_id == client_id)
    return paginate(db, stmt, page, page_size)


def create(db: Session, data: dict[str, Any]) -> Script:
    """插入并提交。"""
    obj = Script(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, obj: Script, data: dict[str, Any]) -> Script:
    """按传入字段更新并提交。"""
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, obj: Script) -> None:
    """删除并提交；存在 audits 时由外键 RESTRICT 拦住。"""
    db.delete(obj)
    db.commit()


def count_by_client(db: Session, client_id: int) -> int:
    """统计某机构名下话术数（删除机构前的引用检查）。"""
    stmt = select(func.count()).select_from(Script).where(Script.client_id == client_id)
    return int(db.execute(stmt).scalar_one())
