"""rules 业务编排：落实铁律 7「改规则必须 version + 1 并存旧版」。

更新策略：
- 只改 enabled（启停）-> 原地更新，不算改规则内容，不 bump
- 改了 axis / law_article / pattern / level / example_bad 任一项 ->
  旧行置 enabled=0 保留不动，插入一条新行，version = 旧 version + 1，返回新行
"""

from sqlalchemy.orm import Session

from backend.core.config import DEFAULT_RULE_VERSION, RuleAxis
from backend.core.errors import BusinessValidationError
from backend.crud.special import rules as crud
from backend.db.models import Rule
from backend.schemas.business import RuleCreate, RuleUpdate
from backend.services.common import get_or_404, update_fields

RESOURCE = "rule"
# 改这些字段视为"改规则内容"，必须走版本化
VERSIONED_FIELDS = frozenset({"axis", "law_article", "pattern", "level", "example_bad"})
VALID_AXES = frozenset(a.value for a in RuleAxis)


def _ensure_axis(axis: str | None) -> None:
    """axis 不在 8 轴枚举内 -> 422（api_spec.md §3.1）。"""
    if axis is not None and axis not in VALID_AXES:
        raise BusinessValidationError(
            f"axis={axis} 不在规则轴枚举内，可选：{sorted(VALID_AXES)}"
        )


def get(db: Session, rule_id: int) -> Rule:
    """取规则，不存在 404。"""
    return get_or_404(crud.get, db, RESOURCE, rule_id)


def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Rule], int]:
    """分页列表。"""
    return crud.list_paged(db, page, page_size)


def create(db: Session, payload: RuleCreate) -> Rule:
    """新增规则，version 固定从 1 开始。"""
    _ensure_axis(payload.axis)
    data = payload.model_dump(mode="json")
    data["version"] = DEFAULT_RULE_VERSION
    return crud.create(db, data)


def update(db: Session, rule_id: int, payload: RuleUpdate) -> Rule:
    """部分更新；改内容则生成新版本行并停用旧行。"""
    old = get(db, rule_id)
    data = update_fields(payload)
    _ensure_axis(data.get("axis"))
    if data.get("level") is not None:
        data["level"] = data["level"].value
    changed = {
        k for k in VERSIONED_FIELDS if k in data and data[k] != getattr(old, k)
    }
    if not changed:
        return crud.update(db, old, data)

    snapshot = {k: getattr(old, k) for k in VERSIONED_FIELDS}
    snapshot.update({k: data[k] for k in VERSIONED_FIELDS if k in data})
    snapshot["enabled"] = data.get("enabled", old.enabled)
    snapshot["version"] = old.version + 1
    crud.update(db, old, {"enabled": False})
    return crud.create(db, snapshot)


def delete(db: Session, rule_id: int) -> None:
    """删除规则（物理删）。"""
    crud.delete(db, get(db, rule_id))
