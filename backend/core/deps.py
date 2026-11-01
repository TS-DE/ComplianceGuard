"""FastAPI 依赖：数据库会话与当前登录用户。"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.errors import UnauthorizedError
from backend.core.security import decode_access_token
from backend.crud import users as users_crud
from backend.db.session import get_db
from backend.models.users import User

# auto_error=False：缺 Authorization 头时自己抛统一异常，而不是 FastAPI 的裸 403
bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access_token>")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    """从 Bearer token 解析并加载当前用户。

    异常:
        UnauthorizedError: 无 token / token 失效 / 用户不存在或已停用
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("缺少 Authorization: Bearer <token>")
    payload = decode_access_token(credentials.credentials)
    user = users_crud.get_by_username(db, str(payload["sub"]))
    if user is None:
        raise UnauthorizedError("token 对应的用户不存在")
    if not user.is_active:
        raise UnauthorizedError("账号已停用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
