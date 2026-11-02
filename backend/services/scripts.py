"""scripts 业务编排：校验归属机构存在、删除前检查审查记录。"""

from sqlalchemy.orm import Session

from backend.core.errors import BusinessValidationError, ConflictError
from backend.crud import audits as audits_crud
from backend.crud import clients as clients_crud
from backend.crud import scripts as crud
from backend.db.models import Script
from backend.schemas.business import ScriptCreate, ScriptUpdate
from backend.services.common import get_or_404, update_fields

RESOURCE = "script"


def _ensure_client(db: Session, client_id: int) -> None:
    """body 里引用的机构不存在 -> 422（不是 404：路径资源存在，是入参不合法）。"""
    if clients_crud.get(db, client_id) is None:
        raise BusinessValidationError(f"client_id={client_id} 对应的机构不存在")


def get(db: Session, script_id: int) -> Script:
    """取话术，不存在 404。"""
    return get_or_404(crud.get, db, RESOURCE, script_id)


def list_paged(
    db: Session, page: int, page_size: int, client_id: int | None
) -> tuple[list[Script], int]:
    """分页列表，可按机构过滤。"""
    return crud.list_paged(db, page, page_size, client_id)


def create(db: Session, payload: ScriptCreate) -> Script:
    """新增话术。"""
    _ensure_client(db, payload.client_id)
    return crud.create(db, payload.model_dump(mode="json"))


def update(db: Session, script_id: int, payload: ScriptUpdate) -> Script:
    """部分更新；换归属时校验新机构存在。"""
    obj = get(db, script_id)
    data = update_fields(payload)
    if data.get("client_id") is not None:
        _ensure_client(db, data["client_id"])
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value
    return crud.update(db, obj, data)


def delete(db: Session, script_id: int) -> None:
    """删除话术；已有审查记录 -> 409（审计留痕不能被连带删掉）。"""
    obj = get(db, script_id)
    refs = audits_crud.count_by_script(db, script_id)
    if refs:
        raise ConflictError(f"script {script_id} 已有 {refs} 条审查记录，不能删除")
    crud.delete(db, obj)
