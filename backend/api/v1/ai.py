"""鉴权后的 AI 审查与改写入口，仅委托服务层组合根。"""
from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field
from datetime import date
from typing import Literal
from backend.services.compliance import run_redteam, redteam_operations

from backend.core.errors import AppError, CODE_NOT_FOUND
from backend.core.security import CurrentUser, DbSession
from backend.api.v1.resources import require_platform
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


class SourcePreviewRequest(BaseModel):
    """按素材预审：source_id 必填；平台侧可指定机构，商家账号一律被改写成自己机构。"""

    source_id: int = Field(gt=0)
    client_id: int | None = Field(default=None, gt=0)


@router.post("/audit/preview-source", tags=["audit"])
def audit_preview_source(payload: SourcePreviewRequest, db: DbSession,
                         current_user: CurrentUser) -> dict:
    """海报体检：直接审查一份已上传素材，逐条给结论与溯源，**不写 audits 表**。

    A1 在这里调 `parse_source` 自己取内容 —— 商家递来海报或录音时，
    不需要有人先把上面的字抄进文本框。
    商家账号强制按本机构校验，越权即拒。
    """
    from backend.core.security import data_scope

    scoped = data_scope(current_user)
    client_id = scoped if scoped is not None else payload.client_id
    return ok(build_audit_tool(db).review_source(payload.source_id, client_id))


class BatchAuditRequest(BaseModel):
    """一次审查多条话术。

    上限 20 条：单条约 6 秒，20 条已接近 2 分钟，再多会让浏览器超时；
    真正的大批量应当走后台任务，这里明确拒绝而不是假装很快。
    """

    client_id: int = Field(gt=0)
    script_ids: list[int] = Field(min_length=1, max_length=20)


@router.post("/audit/batch", tags=["audit"])
def run_audit_batch(payload: BatchAuditRequest, db: DbSession,
                    current_user: CurrentUser) -> dict:
    """并发审查一批话术，结果顺序与 script_ids 一致。

    为什么改成并发：目标是"尽可能快"，单条耗时几乎全在模型调用上，串行等于把等待乘条数。
    上限取 constants.BATCH_AUDIT_WORKERS=4——不计成本 ≠ 打爆模型接口，也 ≠ 拖到浏览器超时。

    三条约束：① 每个任务自带 Session（SQLAlchemy Session 不是线程安全的，
    把请求级 session 分给多个线程会随机报 detached/DirtyRelation）；
    ② 越权校验仍串行且先于任何调用，一条不属于本机构即整批拒绝；③ 单条失败只标该条。
    """
    from concurrent.futures import ThreadPoolExecutor

    from backend.core.constants import BATCH_AUDIT_WORKERS
    from backend.core.security import data_scope
    from backend.crud.special import scripts as script_repo

    scoped = data_scope(current_user)
    tasks, results = [], [None] * len(payload.script_ids)
    for position, script_id in enumerate(payload.script_ids):
        script = script_repo.get(db, script_id)
        if script is None:
            # 保持既有契约：话术不存在只标该条，不改变整批的状态码（本轮没被要求动这里）
            results[position] = {"script_id": script_id, "error": "话术不存在"}
            continue
        if scoped is not None and script.client_id != scoped:
            raise AppError(CODE_NOT_FOUND, f"话术 {script_id} 不存在")
        tasks.append((position, script_id))

    def one(script_id: int) -> dict:
        from backend.db.session import SessionLocal

        session = SessionLocal()
        try:
            return build_audit_tool(session).run_audit(script_id, scoped or payload.client_id)
        except Exception as exc:  # 单条故障不拖垮整批
            session.rollback()
            return {"script_id": script_id, "error": str(exc)}
        finally:
            session.close()

    workers = max(1, min(BATCH_AUDIT_WORKERS, len(tasks)))
    # pool.map 保序：结果必须与 script_ids 一一对应，界面靠下标回贴到原始素材位置
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for position, outcome in zip([pos for pos, _ in tasks],
                                     pool.map(one, [sid for _, sid in tasks])):
            results[position] = outcome
    return ok({"count": len(results), "results": results,
               "meta": {"workers": workers if tasks else 0, "parallel": len(tasks) > 1}})


class ReviewRequest(BaseModel):
    """人工裁定入参：确认系统判定，或推翻它。"""

    verdict: Literal["confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=500)


def _assert_audit_in_scope(db, audit_id, user):
    """商家只能处理自己机构的审查；越权按 404，不暴露存在性。"""
    from backend.core.security import data_scope
    from backend.crud.audit import AuditRepository as _Repo

    scoped = data_scope(user)
    repo = _Repo(db)
    # repo.audit 返回的是快照 dict（含 script_id），不是 ORM 实例
    snapshot = repo.audit(audit_id)
    if snapshot is None:
        raise AppError(CODE_NOT_FOUND, f"审查记录 {audit_id} 不存在")
    if scoped is not None:
        script = repo.script(snapshot["script_id"])
        if not script or script.get("client_id") != scoped:
            raise AppError(CODE_NOT_FOUND, f"审查记录 {audit_id} 不存在")
    return snapshot


@router.get("/audit/review-queue", tags=["audit"])
def review_queue(db: DbSession, current_user: CurrentUser,
                 status: Annotated[str | None, Query(max_length=20)] = "pending",
                 page: Annotated[int, Query(ge=1)] = 1,
                 page_size: Annotated[int, Query(ge=1, le=100)] = 20) -> dict:
    """待人工复核队列（L3 人机回环的入口）。

    只列"机器拿不准"的记录：判定未完成、疑似（分级降级）、或分数为 1。
    商家只看到自己机构的记录。
    """
    from backend.core.security import data_scope
    from backend.crud.audit import AuditRepository
    from backend.crud.special import scripts as script_repo

    scoped = data_scope(current_user)
    rows, total = AuditRepository(db).review_queue(
        status=status or None, client_id=scoped, page=page, page_size=page_size)
    ids = {row.script_id for row in rows}
    contents = {}
    if ids:
        from sqlalchemy import select

        from backend.db.models import Script

        contents = dict(db.execute(
            select(Script.id, Script.content).where(Script.id.in_(ids))).all())
    items = [{
        "id": row.id,
        "script_id": row.script_id,
        "script_content": contents.get(row.script_id),
        "score": row.score,
        "hit_count": row.hit_count,
        "incomplete": row.incomplete,
        "hits": [h for h in (row.hits_json or []) if h.get("status") == "active"],
        "review_status": row.review_status,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]
    return ok(items, total=total)


@router.post("/audit/{audit_id}/review", tags=["audit"])
def review_audit(audit_id: Annotated[int, Path(gt=0)], payload: ReviewRequest,
                 db: DbSession, current_user: CurrentUser) -> dict:
    """人工裁定：confirmed=认定系统判定正确；dismissed=认定机器判错。

    裁定结论是系统准确率的真值来源，因此不可重复覆盖（见仓储层）。
    """
    from backend.crud.audit import AuditRepository

    _assert_audit_in_scope(db, audit_id, current_user)
    row = AuditRepository(db).review(audit_id, payload.verdict,
                                     current_user.id, payload.note)
    return ok({"id": row.id, "review_status": row.review_status,
               "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None})


@router.get("/audit/review-stats", tags=["audit"])
def review_stats(db: DbSession, current_user: CurrentUser) -> dict:
    """复核统计：待办数 + 人工与机器的一致率（分母只算已裁定）。"""
    from backend.core.security import data_scope
    from backend.crud.audit import AuditRepository

    return ok(AuditRepository(db).review_stats(client_id=data_scope(current_user)))


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
    """一次生成并顺序裁判，返回可查询run_id。

    平台级功能：压测会生成违规样本并消耗模型额度，商家账号一律 403。
    """
    require_platform(current_user)
    return ok(run_redteam(db,payload.client_id,payload.scenes,payload.axes))


@router.get('/redteam/{run_id}/gaps',tags=['redteam'])
def redteam_gaps(run_id: str, db: DbSession, current_user: CurrentUser):
    """返回FN/FP清单与含未判定的矩阵。"""
    require_platform(current_user)
    return ok(redteam_operations(db)['repository'].gaps(run_id))


@router.get('/reports/daily',tags=['reports'])
def daily_report(date: date, db: DbSession, current_user: CurrentUser):
    """纯SQL聚合日报，默认不调用模型。

    商家账号只统计自己机构：平台级汇总不能对商家开放。
    """
    from backend.core.security import data_scope
    scoped = data_scope(current_user)
    return ok(redteam_operations(db)['report'].daily(date, scoped if scoped and scoped > 0 else None))


@router.get('/reports/redteam/{run_id}',tags=['reports'])
def redteam_report(run_id: str, db: DbSession, current_user: CurrentUser):
    """固定模板压测报告，不生成任何新事实。"""
    require_platform(current_user)
    return ok(redteam_operations(db)['report'].redteam(run_id))


REDTEAM_AXES = ('efficacy_claim', 'safety_guarantee', 'absolute_terms', 'inducement')


@router.get('/redteam/options', tags=['redteam'])
def redteam_options(db: DbSession, current_user: CurrentUser):
    """返回本轮压测将使用的轴定义、模型与样本计划。

    没有这个接口时，管理员只看到"16 条"，不知道测的是什么轴、用的哪版规则——
    压测结果就没法解释，也没法和规则改动对应起来。

    必须挡住商家：响应里带着每条轴的 pattern / law_article / detector / version，
    等于把判定规则本身交给被审查方。前端菜单藏起来不算数，要在这层拒。
    """
    require_platform(current_user)
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
