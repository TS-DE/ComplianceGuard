"""罚单案例文件模型（data/cases/*.json，db_schema.md §2.2）。

锚点集铁律：内容必须来自监管公开罚单原文，禁止 AI 生成"标准答案"。
本模型只做结构校验，不改善任何字句。
"""

from pydantic import BaseModel, Field, field_validator


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
