"""clients 表读写：纯数据库操作。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.crud.base import paginate
from backend.db.models import Client


def get(db: Session, client_id: int) -> Client | None:
    """按主键取机构，不存在返回 None。"""
    return db.get(Client, client_id)


def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Client], int]:
    """按 id 倒序分页。"""
    stmt = select(Client).order_by(Client.id.desc())
    return paginate(db, stmt, page, page_size)


def create(db: Session, data: dict[str, Any]) -> Client:
    """插入并提交。"""
    obj = Client(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, obj: Client, data: dict[str, Any]) -> Client:
    """按传入字段更新并提交（data 已剔除 None）。"""
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, obj: Client) -> None:
    """删除并提交；有下游引用时由外键 RESTRICT 拦住，异常上抛给调用方。"""
    db.delete(obj)
    db.commit()
