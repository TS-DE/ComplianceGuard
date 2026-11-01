"""rules 表读写：纯数据库操作。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.crud.base import paginate
from backend.models.rules import Rule


def get(db: Session, rule_id: int) -> Rule | None:
    """按主键取规则。"""
    return db.get(Rule, rule_id)


def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Rule], int]:
    """按 id 倒序分页。"""
    stmt = select(Rule).order_by(Rule.id.desc())
    return paginate(db, stmt, page, page_size)


def create(db: Session, data: dict[str, Any]) -> Rule:
    """插入并提交。"""
    obj = Rule(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, obj: Rule, data: dict[str, Any]) -> Rule:
    """按传入字段更新并提交。"""
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, obj: Rule) -> None:
    """删除并提交。"""
    db.delete(obj)
    db.commit()
