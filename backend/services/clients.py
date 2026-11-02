"""clients 业务编排：删除前检查下游话术。"""

from sqlalchemy.orm import Session

from backend.core.errors import ConflictError
from backend.crud import clients as crud
from backend.crud import scripts as scripts_crud
from backend.db.models import Client
from backend.schemas.clients import ClientCreate, ClientUpdate
from backend.services.common import get_or_404, update_fields

RESOURCE = "client"


def get(db: Session, client_id: int) -> Client:
    """取机构，不存在 404。"""
    return get_or_404(crud.get, db, RESOURCE, client_id)


def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Client], int]:
    """分页列表。"""
    return crud.list_paged(db, page, page_size)


def create(db: Session, payload: ClientCreate) -> Client:
    """新增机构。"""
    return crud.create(db, payload.model_dump())


def update(db: Session, client_id: int, payload: ClientUpdate) -> Client:
    """部分更新。"""
    return crud.update(db, get(db, client_id), update_fields(payload))


def delete(db: Session, client_id: int) -> None:
    """删除机构；名下有话术 -> 409（与外键 RESTRICT 一致，提前给可读提示）。"""
    obj = get(db, client_id)
    refs = scripts_crud.count_by_client(db, client_id)
    if refs:
        raise ConflictError(f"client {client_id} 名下仍有 {refs} 条话术，不能删除")
    crud.delete(db, obj)
