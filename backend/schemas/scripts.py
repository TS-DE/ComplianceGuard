"""scripts 请求/响应模型（api_spec.md §3.1）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.core.constants import ScriptStatus


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
