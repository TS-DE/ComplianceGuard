"""素材摄取与素材档案路由。

为什么单独成一个领域子包而不是继续堆在 resources.py 里：
resources.py 装的是"四套同构 CRUD"，它的变化原因是**加一套资源**；
这里的变化原因是**加一种文件格式或加一个引擎**。两种变化原因写进同一个文件，
改 OCR 的人会碰到 CRUD 工厂，改 CRUD 的人会碰到 multipart 参数——
而且 resources.py 已经因此顶到 307 行，越过 CLAUDE.md 的单文件上限。
按 §3.1，目录实文件数不许超过 3，所以走子包而不是新增第四个平铺文件。

多租户约束仍留在这一层：`data_scope` 决定"当前账号能碰哪些机构的素材"，
写在这里是因为漏一处就是越权，而漏在 service 里还有一层兜底。
"""

from typing import Annotated
import json
import mimetypes

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from backend.api.v1.resources import Page
from backend.core.errors import AppError, BusinessValidationError
from backend.core.security import CurrentUser, DbSession, data_scope
from backend.parse import MAX_CHUNKS, MODES, capabilities
from backend.schemas.common import ok
from backend.schemas.business import SourceOut
from backend.services.compliance import ingest, sources

IMPORT_MODE_PATTERN = f"^({'|'.join(MODES)})$"
router = APIRouter()


def _picked_items(items: str | None) -> list[str] | None:
    """解析勾选回来的条目。刻意只收文本、不收前端传来的页码与置信度：
    溯源一律服务端重算，否则"第 3 页"就成了客户端想写什么就写什么的数据。
    """
    if not items:
        return None
    try:
        parsed = json.loads(items)
    except ValueError:
        raise BusinessValidationError("items 必须是 JSON 字符串数组") from None
    if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
        raise BusinessValidationError("items 必须是 JSON 字符串数组")
    picked = [x.strip() for x in parsed if x.strip()][:MAX_CHUNKS]
    if not picked:
        raise BusinessValidationError("勾选的条目为空")
    return picked


@router.post("/scripts/import", tags=["scripts"])
def import_scripts(
    db: DbSession,
    current_user: CurrentUser,
    client_id: Annotated[int, Form(gt=0)],
    scene: Annotated[str | None, Form(max_length=50)] = None,
    commit: Annotated[bool, Form()] = False,
    mode: Annotated[str, Form(pattern=IMPORT_MODE_PATTERN)] = "blank",
    text: Annotated[str | None, Form()] = None,
    items: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
) -> dict:
    """商家素材摄取：粘贴或上传（文档/表格/PPT/PDF/海报图/录音）→ 预览 → 勾选入库。

    两段式是刻意的：切分不可能百分百正确，一键写库等于让脏数据污染审计统计。
    预览阶段既不写库也不落盘，只有 commit=true 才留下原始素材。
    """
    scoped = data_scope(current_user)
    if scoped is not None:
        client_id = scoped  # 商家只能往自己机构导

    raw = b""
    filename = ""
    if file is not None:
        raw = file.file.read()
        filename = file.filename or ""
    elif not (text and text.strip()):
        raise BusinessValidationError("请上传文件或粘贴文本")

    picked = _picked_items(items)
    if not commit:
        return ok(ingest.preview(filename, raw, mode, text))
    return ok(ingest.commit(db, client_id, scene or None, current_user.id,
                            filename, raw, mode, picked, text))


def _owned_source(db: DbSession, source_id: int, current_user):
    """商家只能碰自己机构的素材；对不上一律按 404 处理，不暴露"这条记录存在"。"""
    obj = sources.get(db, source_id)
    scoped = data_scope(current_user)
    if scoped is not None and obj.client_id != scoped:
        raise AppError(404, f"source {source_id} 不存在")
    return obj


@router.get("/sources/formats", tags=["sources"])
def source_formats(current_user: CurrentUser) -> dict:
    """上传页能力清单：能吃哪些扩展名、缺什么引擎、有几种切分模式。

    由解析注册表现算而不是手写清单：手写的一定会和代码不同步，
    不同步的结果是用户传上来才知道"其实不支持"。
    """
    return ok(capabilities())


@router.get("/sources", tags=["sources"])
def list_sources(db: DbSession, page: Page, current_user: CurrentUser,
                 client_id: Annotated[int | None, Query(gt=0)] = None) -> dict:
    """素材档案列表；商家只能看到自己机构上传的。"""
    scoped = data_scope(current_user)
    rows, total = sources.list_paged(
        db, page.page, page.page_size, scoped if scoped is not None else client_id)
    return ok([SourceOut.model_validate(row).model_dump(mode="json") for row in rows],
              total=total)


@router.get("/sources/{source_id}", tags=["sources"])
def get_source(source_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    """素材详情 + 它切出来的话术：溯源抽屉一次拿全。"""
    obj = _owned_source(db, source_id, current_user)
    payload = SourceOut.model_validate(obj).model_dump(mode="json")
    payload["scripts"] = [
        {"id": row.id, "content": row.content, "status": row.status,
         "ref": row.source_ref, "confidence": row.parse_confidence}
        for row in sources.scripts(db, source_id)]
    return ok(payload)


@router.get("/sources/{source_id}/file", tags=["sources"])
def get_source_file(source_id: int, db: DbSession,
                    current_user: CurrentUser) -> FileResponse:
    """原始素材内联预览：海报直接显示、录音直接播、PDF 直接翻。

    inline 而不是 attachment：商家点开是为了核对"海报上到底印的哪句"，
    每次弹下载就等于没给核对入口。
    """
    obj = _owned_source(db, source_id, current_user)
    path = sources.file_path(db, obj.id)
    media_type, _encoding = mimetypes.guess_type(obj.filename)
    return FileResponse(path, media_type=media_type or "application/octet-stream",
                        filename=obj.filename, content_disposition_type="inline")
