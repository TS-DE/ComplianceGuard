"""鉴权后的 AI 审查与改写入口，仅委托服务层组合根。"""
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from datetime import date
from typing import Literal
from backend.services.compliance import run_redteam, redteam_operations

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



class RedteamRunRequest(BaseModel):
    """固定递进矩阵含真合规对照组。"""
    client_id: int = Field(gt=0)
    scenes: list[str] = Field(min_length=1,max_length=1)
    axes: list[Literal['efficacy_claim','safety_guarantee','absolute_terms','inducement']] = Field(min_length=1,max_length=4)
    strength: Literal['all'] = 'all'


@router.post('/redteam/run',tags=['redteam'])
def redteam_run(payload: RedteamRunRequest, db: DbSession, current_user: CurrentUser):
    """一次生成并顺序裁判，返回可查询run_id。"""
    return ok(run_redteam(db,payload.client_id,payload.scenes,payload.axes))


@router.get('/redteam/{run_id}/gaps',tags=['redteam'])
def redteam_gaps(run_id: str, db: DbSession, current_user: CurrentUser):
    """返回FN/FP清单与含未判定的矩阵。"""
    return ok(redteam_operations(db)['repository'].gaps(run_id))


@router.get('/reports/daily',tags=['reports'])
def daily_report(date: date, db: DbSession, current_user: CurrentUser):
    """纯SQL聚合日报，默认不调用模型。"""
    return ok(redteam_operations(db)['report'].daily(date))


@router.get('/reports/redteam/{run_id}',tags=['reports'])
def redteam_report(run_id: str, db: DbSession, current_user: CurrentUser):
    """固定模板压测报告，不生成任何新事实。"""
    return ok(redteam_operations(db)['report'].redteam(run_id))
