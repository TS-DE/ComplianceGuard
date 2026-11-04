"""鉴权业务编排：注册查重、登录校验、token 签发。"""

import logging

from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, UnauthorizedError
from backend.core.security import create_access_token, hash_password, verify_password
from backend.crud.special import users as users_crud
from backend.db.models import User

logger = logging.getLogger(__name__)


def register(db: Session, username: str, password: str, role: str,
             client_name: str | None = None) -> User:
    """注册新用户；商家账号会同时创建并绑定一个机构。

    为什么要一起建机构：商家注册后必须立刻能上传自己机构的话术，
    若要求先由管理员建机构再分配账号，自助端就失去了意义。

    异常:
        ConflictError: 用户名已存在 -> 409
    """
    if users_crud.get_by_username(db, username) is not None:
        raise ConflictError(f"用户名 {username} 已存在")

    client_id = None
    if role == "merchant":
        from backend.crud.special import clients as clients_crud

        name = (client_name or username).strip() or username
        client = clients_crud.create(db, {"name": name, "industry": "medical_beauty", "plan": "free"})
        client_id = client.id

    return users_crud.create(db, username, hash_password(password), role, client_id)


def authenticate(db: Session, username: str, password: str) -> User:
    """校验账号密码。

    异常:
        UnauthorizedError: 用户不存在 / 密码错误 / 账号被停用
    注意:
        用户不存在与密码错误返回同一提示，避免账号枚举。
    """
    user = users_crud.get_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("用户名或密码错误")
    if not user.is_active:
        raise UnauthorizedError("账号已停用")
    return user


def issue_token(user: User) -> str:
    """为用户签发 access_token，附带 role 声明供前端展示。"""
    return create_access_token(subject=user.username, extra={"role": user.role})
