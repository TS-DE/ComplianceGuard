"""同构资源路由工厂，保持路径、参数与返回体契约。"""
from typing import Annotated
import json

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from backend.core.errors import BusinessValidationError
from backend.core.security import CurrentUser, DbSession, get_current_user
from backend.core.config import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from backend.schemas.common import PageParams, ok
from backend.schemas.business import (
    ClientCreate, ClientOut, ClientUpdate, ScriptCreate, ScriptOut, ScriptUpdate,
    AuditCreate, AuditOut, AuditUpdate, RuleCreate, RuleOut, RuleUpdate,
)
from backend.services.compliance import clients, scripts, audits, rules
from backend.tools.extract_tool import MAX_CHUNKS, extract_text, split_scripts


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

    def list_scripts(db: DbSession, page: Page,
                     client_id: Annotated[int | None, Query(gt=0)] = None,
                     q: Annotated[str | None, Query(max_length=500)] = None) -> dict:
        """纯查询走仓储，避免为过滤参数改动审查编排。"""
        from backend.crud.special import scripts as script_repo
        rows, total = script_repo.list_paged(db, page.page, page.page_size, client_id, q)
        return ok([output(row) for row in rows], total=total)

    def list_audits(db: DbSession, page: Page,
                    client_id: Annotated[int | None, Query(gt=0)] = None,
                    script_id: Annotated[int | None, Query(gt=0)] = None) -> dict:
        """审查记录列表：可按机构或单条话术过滤。

        script_id 支撑「从话术库跳到该话术的审查历史」——一条话术可能被多次审查，
        返回的是历史列表而非只取最新一条。
        """
        rows, total = service.list_paged(db, page.page, page.page_size, client_id, script_id)
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


@router.post("/scripts/import", tags=["scripts"])
def import_scripts(
    db: DbSession,
    current_user: CurrentUser,
    client_id: Annotated[int, Form(gt=0)],
    scene: Annotated[str | None, Form(max_length=50)] = None,
    commit: Annotated[bool, Form()] = False,
    mode: Annotated[str, Form(pattern="^(blank|line)$")] = "blank",
    text: Annotated[str | None, Form()] = None,
    items: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
) -> dict:
    """商家文案批量导入：粘贴整段文本或上传文档，切成多条后预览 / 入库。

    两段式（先预览后入库）是刻意的：切分结果必须让人确认，
    否则一次传错文件就把脏数据写进库里，后面所有审计统计都被污染。
    """
    if file is not None:
        raw = file.file.read()
        source = f"file:{file.filename}"
        try:
            content = extract_text(file.filename or "", raw)
        except ValueError as exc:
            raise BusinessValidationError(str(exc)) from None
    elif text and text.strip():
        source = "text"
        content = text
    else:
        raise BusinessValidationError("请上传文件或粘贴文本")

    # 入库时可以只提交用户在预览里勾选的条目：切分不可能百分百正确，
    # 必须允许人工在写库前剔除误切片段，否则脏数据会污染后面所有审计统计。
    if items:
        try:
            parsed = json.loads(items)
        except ValueError:
            raise BusinessValidationError("items 必须是 JSON 字符串数组") from None
        if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
            raise BusinessValidationError("items 必须是 JSON 字符串数组")
        pieces = [x.strip() for x in parsed if x.strip()][:MAX_CHUNKS]
        if not pieces:
            raise BusinessValidationError("勾选的条目为空")
    else:
        try:
            pieces = split_scripts(content, mode)
        except ValueError as exc:
            raise BusinessValidationError(str(exc)) from None
    if not pieces:
        raise BusinessValidationError("未从内容中切分出有效话术（可能过短或格式不支持）")

    created: list[int] = []
    if commit:
        for piece in pieces:
            row = scripts.create(db, ScriptCreate(
                client_id=client_id, scene=scene or None, content=piece))
            created.append(row.id)
    return ok({
        "source": source,
        "count": len(pieces),
        "items": pieces,
        "created": len(created),
        "script_ids": created,
    })


for spec in [
    ("clients", clients, ClientCreate, ClientUpdate, ClientOut, False),
    ("scripts", scripts, ScriptCreate, ScriptUpdate, ScriptOut, True),
    ("audits", audits, AuditCreate, AuditUpdate, AuditOut, True),
    ("rules", rules, RuleCreate, RuleUpdate, RuleOut, False),
]:
    router.include_router(resource_router(*spec))
