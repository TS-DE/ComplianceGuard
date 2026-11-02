"""clients 请求/响应模型（api_spec.md §3.1）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
