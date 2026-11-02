"""同构资源路由工厂，保持路径、参数与返回体契约。"""
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from backend.core.security import DbSession, get_current_user
from backend.core.config import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from backend.schemas.common import PageParams, ok
from backend.schemas.business import (
    ClientCreate, ClientOut, ClientUpdate, ScriptCreate, ScriptOut, ScriptUpdate,
    AuditCreate, AuditOut, AuditUpdate, RuleCreate, RuleOut, RuleUpdate,
)
from backend.services.compliance import clients, scripts, audits, rules


def page_params(
    page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    """将 query 参数收拢为分页对象；越界交给统一异常处理。"""
    return PageParams(page=page, page_size=page_size)


Page = Annotated[PageParams, Depends(page_params)]


def resource_router(name, service, create_schema, update_schema, out_schema, filtered=False):
    """构造同构 CRUD 路由；schema 绑定在函数注解中供 FastAPI 校验。"""
    router = APIRouter(prefix=f"/{name}", tags=[name], dependencies=[Depends(get_current_user)])

    def output(obj):
        return out_schema.model_validate(obj).model_dump(mode="json")

    def list_items(db: DbSession, page: Page) -> dict:
        rows, total = service.list_paged(db, page.page, page.page_size)
        return ok([output(row) for row in rows], total=total)

    def list_filtered(db: DbSession, page: Page,
                      client_id: Annotated[int | None, Query(gt=0)] = None) -> dict:
        rows, total = service.list_paged(db, page.page, page.page_size, client_id)
        return ok([output(row) for row in rows], total=total)

    def get_item(item_id: int, db: DbSession) -> dict:
        return ok(output(service.get(db, item_id)))

    def create_item(payload: create_schema, db: DbSession) -> dict:
        return ok(output(service.create(db, payload)))

    def update_item(item_id: int, payload: update_schema, db: DbSession) -> dict:
        return ok(output(service.update(db, item_id, payload)))

    def delete_item(item_id: int, db: DbSession) -> dict:
        service.delete(db, item_id)
        return ok({"id": item_id})

    router.add_api_route("", list_filtered if filtered else list_items, methods=["GET"])
    router.add_api_route("/{item_id}", get_item, methods=["GET"])
    router.add_api_route("", create_item, methods=["POST"])
    router.add_api_route("/{item_id}", update_item, methods=["PUT"])
    router.add_api_route("/{item_id}", delete_item, methods=["DELETE"])
    return router


router = APIRouter()
for spec in [
    ("clients", clients, ClientCreate, ClientUpdate, ClientOut, False),
    ("scripts", scripts, ScriptCreate, ScriptUpdate, ScriptOut, True),
    ("audits", audits, AuditCreate, AuditUpdate, AuditOut, True),
    ("rules", rules, RuleCreate, RuleUpdate, RuleOut, False),
]:
    router.include_router(resource_router(*spec))
