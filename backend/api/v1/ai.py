"""鉴权后的 AI 审查与改写入口，仅委托服务层组合根。"""
from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field
from datetime import date
from typing import Literal
from backend.services.compliance import run_redteam, redteam_operations

from backend.core.errors import AppError, CODE_NOT_FOUND
from backend.core.security import CurrentUser, DbSession
from backend.rag.ingest import find_law_article
from backend.schemas.common import ok
from backend.services.compliance import audit_operations as build_audit_tool

router = APIRouter()


@router.get("/law/article", tags=["law"])
def law_article_original(
    current_user: CurrentUser,
    code: Annotated[str, Query(min_length=2, max_length=80, description="命中法条的 code，如 广告法第16条")],
    item_no: Annotated[str | None, Query(max_length=40, description="命中项，如 第十六条(一)")] = None,
) -> dict:
    """返回命中法条（可精确到项）的原文，供前端「一键追溯到条文」使用。

    只读本地法规归档，不查向量库、不调用模型，因此可以随时点开而不产生费用。
    """
    found = find_law_article(code, item_no)
    if found is None:
        # AppError 基类接受 (code, msg)：NotFoundException 的签名是 (resource, res_id:int)，
        # 这里 code 是字符串条文标识，直接构造基类更贴合语义。
        raise AppError(CODE_NOT_FOUND, f"法规归档中未收录该条文：{code}")
    return ok(found)


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


REDTEAM_AXES = ('efficacy_claim', 'safety_guarantee', 'absolute_terms', 'inducement')


@router.get('/redteam/options', tags=['redteam'])
def redteam_options(db: DbSession, current_user: CurrentUser):
    """返回本轮压测将使用的轴定义、模型与样本计划。

    没有这个接口时，管理员只看到"16 条"，不知道测的是什么轴、用的哪版规则——
    压测结果就没法解释，也没法和规则改动对应起来。
    """
    from backend.rag.embedding import llm_config
    from backend.services.compliance import rules as rule_service

    rows, _ = rule_service.list_paged(db, 1, 100)
    enabled = {row.axis: row for row in rows if row.enabled and row.axis in REDTEAM_AXES}
    axes = [{
        "axis": axis,
        "available": axis in enabled,
        "version": enabled[axis].version if axis in enabled else None,
        "detector": enabled[axis].detector if axis in enabled else None,
        "law_article": enabled[axis].law_article if axis in enabled else None,
        "pattern": enabled[axis].pattern if axis in enabled else None,
    } for axis in REDTEAM_AXES]
    available = sum(1 for item in axes if item["available"])
    return ok({
        "model": llm_config().get("JUDGE_MODEL"),
        "axes": axes,
        "plan": {
            "per_axis_samples": 4,
            "description": "每个目标轴生成 low / mid / high 三档递进话术 + 1 条合规对照",
            "sample_total_for_all_axes": available * 4,
            "expected_seconds": "约 2-3 分钟",
            "note": "合规对照用于计算误杀率：全部样本都是‘预期违规’时，误杀率没有分母。",
        },
    })
