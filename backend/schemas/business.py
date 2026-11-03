"""业务资源与罚单的输入输出契约。"""
from datetime import datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend.core.config import VALID_SCORES, RuleLevel, ScriptStatus


class ClientBase(BaseModel):
    """机构公共字段。"""

    name: str = Field(min_length=1, max_length=100)
    industry: str = Field(default="medical_beauty", max_length=50)
    contact: str | None = Field(default=None, max_length=100)
    plan: str = Field(default="free", max_length=30)

class ClientCreate(ClientBase):
    """新增：只有 name 必填。"""

class ClientUpdate(BaseModel):
    """修改：全部可选，未传字段保持不变。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    industry: str | None = Field(default=None, max_length=50)
    contact: str | None = Field(default=None, max_length=100)
    plan: str | None = Field(default=None, max_length=30)

class ClientOut(ClientBase):
    """响应：带 id 与创建时间。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

class ScriptBase(BaseModel):
    """话术公共字段。"""

    client_id: int = Field(gt=0)
    scene: str | None = Field(default=None, max_length=50)
    content: str = Field(min_length=1)

class ScriptCreate(ScriptBase):
    """新增：status 缺省 pending，允许调用方显式指定。"""

    status: ScriptStatus = ScriptStatus.PENDING

class ScriptUpdate(BaseModel):
    """修改：全部可选；client_id 允许换归属。"""

    client_id: int | None = Field(default=None, gt=0)
    scene: str | None = Field(default=None, max_length=50)
    content: str | None = Field(default=None, min_length=1)
    status: ScriptStatus | None = None

class ScriptOut(ScriptBase):
    """响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime

class AuditBase(BaseModel):
    """审查记录公共字段。"""

    script_id: int = Field(gt=0)
    score: int = Field(description="2 合规 / 1 轻微 / 0 违规 / -1 未完成")
    hit_count: int = Field(default=0, ge=0)
    hits_json: list[dict[str, Any]] | None = None
    law_refs_json: list[dict[str, Any]] | None = None
    rewritten_text: str | None = None
    rewrite_passed: bool | None = None
    model: str | None = Field(default=None, max_length=50)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    latency_ms: int = Field(default=0, ge=0)
    incomplete: bool = False

    @field_validator("score")
    @classmethod
    def _check_score(cls, value: int) -> int:
        # 与库侧 ck_audits_score 同源：这里先挡，好给出可读的 400 而不是 409
        if value not in VALID_SCORES:
            raise ValueError(f"score 只能是 {list(VALID_SCORES)}，收到 {value}")
        return value

class AuditCreate(AuditBase):
    """新增（调试用）。"""

class AuditUpdate(BaseModel):
    """修改：全部可选。"""

    score: int | None = None
    hit_count: int | None = Field(default=None, ge=0)
    hits_json: list[dict[str, Any]] | None = None
    law_refs_json: list[dict[str, Any]] | None = None
    rewritten_text: str | None = None
    rewrite_passed: bool | None = None
    model: str | None = Field(default=None, max_length=50)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    incomplete: bool | None = None

    @field_validator("score")
    @classmethod
    def _check_score(cls, value: int | None) -> int | None:
        if value is not None and value not in VALID_SCORES:
            raise ValueError(f"score 只能是 {list(VALID_SCORES)}，收到 {value}")
        return value

class AuditOut(BaseModel):
    """响应：字段与 db_schema.md §1.4 全量对齐。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    script_id: int
    score: int
    hit_count: int
    hits_json: list[dict[str, Any]] | None
    law_refs_json: list[dict[str, Any]] | None
    rewritten_text: str | None
    rewrite_passed: bool | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    # 2026-11-03：audits.cost 已迁移为可空（NULL=未配置单价未计价，0=确为零成本）。
    # 此处必须同步为可空，否则遇到 cost 为 NULL 的历史行会抛 ValidationError，
    # 导致 GET /audits 列表整体 500（详情正常，因为那条恰好 cost 有值）。
    cost: Decimal | None = Field(default=None, ge=0)
    latency_ms: int
    incomplete: bool
    created_at: datetime

class RuleBase(BaseModel):
    """规则公共字段。

    axis 用 str 而不是 RuleAxis：契约要求越界返回 422（业务校验），
    若交给 Pydantic 枚举会变成 400（参数校验），所以放到服务层判。
    """

    axis: str = Field(min_length=1, max_length=40)
    law_article: str = Field(min_length=1, max_length=80)
    pattern: str = Field(min_length=1, max_length=200)
    level: RuleLevel
    example_bad: str | None = None
    enabled: bool = True

class RuleCreate(RuleBase):
    """新增：version 由服务层决定，调用方不能直接塞。"""

class RuleUpdate(BaseModel):
    """修改：全部可选。"""

    axis: str | None = Field(default=None, min_length=1, max_length=40)
    law_article: str | None = Field(default=None, min_length=1, max_length=80)
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    level: RuleLevel | None = None
    example_bad: str | None = None
    enabled: bool | None = None

class RuleOut(RuleBase):
    """响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    created_at: datetime
    updated_at: datetime

class CaseRecord(BaseModel):
    """一条官方罚单案例。"""

    case_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    year: int = Field(ge=2000, le=2100)
    penalty_amount: int = Field(ge=0, description="罚款金额，单位为元")
    violation_quote: str = Field(min_length=1, description="违规原话，逐字，不得改写")
    official_ruling: str = Field(min_length=1, description="官方定性原文")
    law_articles: list[str] = Field(min_length=1)
    category: str = Field(min_length=1)
    source: str | None = Field(default=None, description="出处说明，便于人工回溯核对")

    @field_validator("violation_quote")
    @classmethod
    def _quote_not_placeholder(cls, value: str) -> str:
        # 防止用占位符充当锚点（锚点必须可回溯到罚单原文）
        if value.strip().upper().startswith("TODO") or len(value.strip()) < 6:
            raise ValueError("violation_quote 必须是罚单原文，不得使用占位符")
        return value
