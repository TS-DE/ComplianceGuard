"""audits 请求/响应模型（api_spec.md §3.1）。

D1 仅读 + 手工建（调试用）；正式写入由 D3 审查 Agent 负责。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.constants import VALID_SCORES


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
    cost: Decimal
    latency_ms: int
    incomplete: bool
    created_at: datetime
