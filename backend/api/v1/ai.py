"""鉴权后的 AI 审查与改写入口，仅委托服务层组合根。"""
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

from backend.core.security import CurrentUser, DbSession
from backend.schemas.common import ok
from backend.services.compliance import audit_operations as build_audit_tool

router = APIRouter()


class AuditRunRequest(BaseModel):
    """已存话术的审查请求，机构必须与话术归属一致。"""

    script_id: int = Field(gt=0)
    client_id: int = Field(gt=0)


@router.post("/audit/run", tags=["audit"])
def run_audit(payload: AuditRunRequest, db: DbSession, current_user: CurrentUser) -> dict:
    """鉴权后运行完整审查；保留不完整状态与免责声明。"""
    return ok(build_audit_tool(db).run_audit(payload.script_id, payload.client_id))


@router.post("/audit/{audit_id}/rewrite", tags=["audit"])
def rewrite_audit(audit_id: Annotated[int, Path(gt=0)], db: DbSession,
                  current_user: CurrentUser) -> dict:
    """鉴权后生成并复核改写，返回可审计的复核结果。"""
    return ok(build_audit_tool(db).rewrite_audit(audit_id))
