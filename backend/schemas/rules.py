"""rules 请求/响应模型（api_spec.md §3.1）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.core.constants import RuleLevel


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
