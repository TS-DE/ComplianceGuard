"""通用分页查询：四套 CRUD 共用同一形状，避免各写一遍 offset/limit。

单独抽出来的原因：分页 + total 的口径必须一致，否则 total 与实际返回条数会打架。
"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def paginate(
    db: Session, stmt: Select, page: int, page_size: int
) -> tuple[list[Any], int]:
    """执行分页查询。

    入参:
        stmt: 已带过滤条件的 select()
        page: 页码（从 1 开始）
        page_size: 每页条数
    返回:
        (本页数据列表, 过滤后的总条数)
    """
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return list(rows), int(total)


class Repository:
    """组合模型的通用持久化操作；事务提交语义与原 CRUD 一致。"""

    def __init__(self, model):
        self.model = model

    def create(self, db, data):
        obj = self.model(**data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db, obj, data):
        for field, value in data.items():
            setattr(obj, field, value)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db, obj):
        db.delete(obj)
        db.commit()
