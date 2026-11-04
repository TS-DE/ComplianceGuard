"""鉴权相关请求/响应模型（api_spec.md §2）。"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.config import UserRole
from backend.core.security import MIN_PASSWORD_LENGTH

Username = Annotated[str, Field(min_length=3, max_length=50)]
Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)]


class RegisterRequest(BaseModel):
    """注册入参；role 缺省 operator。"""

    username: Username
    password: Password
    role: UserRole = UserRole.OPERATOR
    # 商家注册时用该名称建机构并绑定；管理员忽略此字段
    client_name: str | None = Field(default=None, max_length=100)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        # 用户名前后空格没有实义，统一去掉，避免 "a" 与 "a " 两个账号
        value = value.strip()
        if not value:
            raise ValueError("用户名不能为空")
        return value


class LoginRequest(BaseModel):
    """登录入参。"""

    username: Username
    password: Password


class UserBrief(BaseModel):
    """返回体里的用户摘要（不含任何哈希）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    client_id: int | None = None


class UserDetail(UserBrief):
    """GET /auth/me 的返回：多一个创建时间。"""

    created_at: datetime


class TokenData(BaseModel):
    """登录成功返回。"""

    access_token: str
    token_type: str = "bearer"
    user: UserBrief
