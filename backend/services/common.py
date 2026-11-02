"""服务层通用工具：取不到就 404、过滤 None 字段。"""

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.errors import NotFoundError

T = TypeVar("T")


def get_or_404(
    getter: Callable[[Session, int], T | None], db: Session, resource: str, res_id: int
) -> T:
    """调用 crud.get，结果为 None 时抛 404。"""
    obj = getter(db, res_id)
    if obj is None:
        raise NotFoundError(resource, res_id)
    return obj


def update_fields(payload: BaseModel) -> dict[str, Any]:
    """只取调用方显式传入的字段（exclude_unset），实现部分更新。

    用 exclude_unset 而不是 exclude_none：允许显式把可空字段改回 null（如 contact）。
    """
    return payload.model_dump(exclude_unset=True, mode="python")
