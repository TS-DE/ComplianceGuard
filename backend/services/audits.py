"""audits 业务编排：D1 只做读 + 调试用手工建。"""

from sqlalchemy.orm import Session

from backend.core.errors import BusinessValidationError
from backend.crud import audits as crud
from backend.crud import scripts as scripts_crud
from backend.db.models import Audit
from backend.schemas.business import AuditCreate, AuditUpdate
from backend.services.common import get_or_404, update_fields

RESOURCE = "audit"


def get(db: Session, audit_id: int) -> Audit:
    """取审查记录，不存在 404。"""
    return get_or_404(crud.get, db, RESOURCE, audit_id)


def list_paged(
    db: Session,
    page: int,
    page_size: int,
    client_id: int | None,
) -> tuple[list[Audit], int]:
    """分页列表，可按机构过滤（经 scripts 关联）。"""
    return crud.list_paged(db, page, page_size, client_id)


def create(db: Session, payload: AuditCreate) -> Audit:
    """手工建审查记录（调试用）；话术必须存在。"""
    if scripts_crud.get(db, payload.script_id) is None:
        raise BusinessValidationError(f"script_id={payload.script_id} 对应的话术不存在")
    return crud.create(db, payload.model_dump())


def update(db: Session, audit_id: int, payload: AuditUpdate) -> Audit:
    """部分更新。"""
    return crud.update(db, get(db, audit_id), update_fields(payload))


def delete(db: Session, audit_id: int) -> None:
    """删除审查记录。"""
    crud.delete(db, get(db, audit_id))
