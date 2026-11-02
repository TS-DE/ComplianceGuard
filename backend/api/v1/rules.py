"""rules 路由：规则 CRUD（api_spec.md §3）。改规则内容会生成新版本行（铁律 7）。"""

from fastapi import APIRouter, Depends

from backend.api.v1.common import Page
from backend.core.security import DbSession, get_current_user
from backend.schemas.common import ok
from backend.schemas.rules import RuleCreate, RuleOut, RuleUpdate
from backend.services import rules as service

# 整组路由挂鉴权依赖：漏写单个接口也不会绕过 JWT
router = APIRouter(
    prefix="/rules", tags=["rules"], dependencies=[Depends(get_current_user)]
)


def _out(obj: object) -> dict:
    return RuleOut.model_validate(obj).model_dump(mode="json")


@router.get("")
def list_items(db: DbSession, page: Page) -> dict:
    """分页列表。"""
    rows, total = service.list_paged(db, page.page, page.page_size)
    return ok([_out(r) for r in rows], total=total)


@router.get("/{item_id}")
def get_item(item_id: int, db: DbSession) -> dict:
    """详情；不存在 404。"""
    return ok(_out(service.get(db, item_id)))


@router.post("")
def create_item(payload: RuleCreate, db: DbSession) -> dict:
    """新增。"""
    return ok(_out(service.create(db, payload)))


@router.put("/{item_id}")
def update_item(item_id: int, payload: RuleUpdate, db: DbSession) -> dict:
    """部分更新；不存在 404。"""
    return ok(_out(service.update(db, item_id, payload)))


@router.delete("/{item_id}")
def delete_item(item_id: int, db: DbSession) -> dict:
    """删除；不存在 404，有下游引用 409。"""
    service.delete(db, item_id)
    return ok({"id": item_id})
