"""同构资源路由工厂，保持路径、参数与返回体契约。

多租户约束集中在这一层：`data_scope` 把「当前账号能看到哪些机构的数据」
收敛为一个可空整数，所有列表与单条读写都必须过它。
把判断放在路由层而不是各 service，是为了避免某个接口漏写就形成越权。
"""
from typing import Annotated
import json

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from backend.core.errors import AppError, BusinessValidationError
from backend.core.security import CurrentUser, DbSession, data_scope, get_current_user
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


def require_platform(user: CurrentUser) -> None:
    """平台级接口（规则库等）只允许管理员/运营访问。

    商家账号能看自己的审查结果，但不应看到或改动判定规则本身——
    否则等于让被审查方修改审查标准。
    """
    if getattr(user, "role", None) == "merchant":
        raise AppError(403, "该功能仅平台管理员可用")


def owned_client_id(db, name: str, obj) -> int | None:
    """取某条资源实际归属的机构 id，用于越权校验。"""
    if name == "clients":
        return obj.id
    if name == "scripts":
        return obj.client_id
    if name == "audits":
        from backend.crud.special import scripts as script_repo

        script = script_repo.get(db, obj.script_id)
        return script.client_id if script else None
    return None


def resource_router(name, service, create_schema, update_schema, out_schema,
                    filtered=False, platform_only=False):
    """构造同构 CRUD 路由；schema 绑定在函数注解中供 FastAPI 校验。"""
    router = APIRouter(prefix=f"/{name}", tags=[name], dependencies=[Depends(get_current_user)])

    def output(obj):
        payload = out_schema.model_validate(obj).model_dump(mode="json")
        return payload

    def attach_script_content(db, rows, payloads):
        """审查记录补上原话术内容。

        用一次 IN 查询批量取，避免每行一次 SELECT；
        话术被删除时留 None，不编造内容。
        """
        if name != "audits" or not rows:
            return payloads
        from sqlalchemy import select

        from backend.db.models import Script

        ids = {row.script_id for row in rows}
        found = db.execute(select(Script.id, Script.content)
                           .where(Script.id.in_(ids))).all()
        content = {sid: text for sid, text in found}
        for row, payload in zip(rows, payloads):
            payload["script_content"] = content.get(row.script_id)
        return payloads

    def assert_owned(db, obj, scoped: int | None) -> None:
        """商家只能操作自己机构的资源；不匹配一律按不存在处理，避免暴露存在性。"""
        if scoped is None:
            return
        if owned_client_id(db, name, obj) != scoped:
            raise AppError(404, f"{name} {getattr(obj, 'id', '?')} 不存在")

    def list_items(db: DbSession, page: Page, current_user: CurrentUser) -> dict:
        scoped = data_scope(current_user)
        if platform_only:
            require_platform(current_user)
        if name == "clients" and scoped is not None:
            row = clients.get(db, scoped)
            rows = [row] if row else []
            return ok([output(item) for item in rows], total=len(rows))
        rows, total = service.list_paged(db, page.page, page.page_size)
        return ok([output(row) for row in rows], total=total)

    def list_filtered(db: DbSession, page: Page, current_user: CurrentUser,
                      client_id: Annotated[int | None, Query(gt=0)] = None) -> dict:
        scoped = data_scope(current_user)
        rows, total = service.list_paged(
            db, page.page, page.page_size, scoped if scoped is not None else client_id)
        return ok([output(row) for row in rows], total=total)

    def list_scripts(db: DbSession, page: Page, current_user: CurrentUser,
                     client_id: Annotated[int | None, Query(gt=0)] = None,
                     q: Annotated[str | None, Query(max_length=500)] = None) -> dict:
        """纯查询走仓储，避免为过滤参数改动审查编排。"""
        from backend.crud.special import scripts as script_repo

        scoped = data_scope(current_user)
        rows, total = script_repo.list_paged(
            db, page.page, page.page_size, scoped if scoped is not None else client_id, q)
        return ok([output(row) for row in rows], total=total)

    def list_audits(db: DbSession, page: Page, current_user: CurrentUser,
                    client_id: Annotated[int | None, Query(gt=0)] = None,
                    script_id: Annotated[int | None, Query(gt=0)] = None) -> dict:
        """审查记录列表：可按机构或单条话术过滤。

        script_id 支撑「从话术库跳到该话术的审查历史」——一条话术可能被多次审查，
        返回的是历史列表而非只取最新一条。
        """
        scoped = data_scope(current_user)
        rows, total = service.list_paged(
            db, page.page, page.page_size, scoped if scoped is not None else client_id, script_id)
        payloads = attach_script_content(db, rows, [output(row) for row in rows])
        return ok(payloads, total=total)

    def get_item(item_id: int, db: DbSession, current_user: CurrentUser) -> dict:
        if platform_only:
            require_platform(current_user)
        obj = service.get(db, item_id)
        assert_owned(db, obj, data_scope(current_user))
        return ok(attach_script_content(db, [obj], [output(obj)])[0])

    def create_item(payload: create_schema, db: DbSession, current_user: CurrentUser) -> dict:
        if platform_only:
            require_platform(current_user)
        scoped = data_scope(current_user)
        # 商家提交时强制落回自己机构，不接受前端传入的 client_id。
        if scoped is not None and hasattr(payload, "client_id"):
            payload = payload.model_copy(update={"client_id": scoped})
        obj = service.create(db, payload)
        assert_owned(db, obj, scoped)
        return ok(output(obj))

    def update_item(item_id: int, payload: update_schema, db: DbSession,
                    current_user: CurrentUser) -> dict:
        if platform_only:
            require_platform(current_user)
        scoped = data_scope(current_user)
        assert_owned(db, service.get(db, item_id), scoped)
        obj = service.update(db, item_id, payload)
        return ok(output(obj))

    def delete_item(item_id: int, db: DbSession, current_user: CurrentUser) -> dict:
        if platform_only:
            require_platform(current_user)
        assert_owned(db, service.get(db, item_id), data_scope(current_user))
        service.delete(db, item_id)
        return ok({"id": item_id})

    listing = (list_scripts if name == 'scripts'
               else list_audits if name == 'audits'
               else list_filtered if filtered else list_items)
    router.add_api_route("", listing, methods=["GET"])
    router.add_api_route("/{item_id}", get_item, methods=["GET"])
    router.add_api_route("", create_item, methods=["POST"])
    router.add_api_route("/{item_id}", update_item, methods=["PUT"])
    router.add_api_route("/{item_id}", delete_item, methods=["DELETE"])
    return router


router = APIRouter()


for spec in [
    ("clients", clients, ClientCreate, ClientUpdate, ClientOut, False, False),
    ("scripts", scripts, ScriptCreate, ScriptUpdate, ScriptOut, True, False),
    ("audits", audits, AuditCreate, AuditUpdate, AuditOut, True, False),
    ("rules", rules, RuleCreate, RuleUpdate, RuleOut, False, True),
]:
    router.include_router(resource_router(*spec))
