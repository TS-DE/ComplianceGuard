"""密码哈希与 JWT 签发/校验。

bcrypt 直接调官方库（4.x）而不是 passlib：passlib 1.7.4 读不到 bcrypt 4.x 的
__about__ 会打 warning，且该组合已不再维护。这里做 72 字节截断，避免超长密码
被静默截断后互相等价。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from backend.core.config import settings
from backend.core.errors import UnauthorizedError

logger = logging.getLogger(__name__)

# bcrypt 算法上限 72 字节，超出部分会被丢弃，所以先显式截断
BCRYPT_MAX_BYTES = 72
MIN_PASSWORD_LENGTH = 6


def _to_bytes(password: str) -> bytes:
    """UTF-8 编码并截到 bcrypt 上限，防止超长密码等价。"""
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希（成本因子取配置）。

    入参:
        password: 明文密码
    返回:
        形如 $2b$12$... 的哈希字符串
    异常:
        ValueError: 密码短于最小长度
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码长度不得少于 {MIN_PASSWORD_LENGTH} 位")
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(_to_bytes(password), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文与哈希是否匹配；哈希格式非法时返回 False，不抛异常。"""
    try:
        return bcrypt.checkpw(_to_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        # 库里存了非 bcrypt 格式的脏数据：按校验失败处理，避免 500
        logger.warning("密码哈希格式非法，按校验失败处理")
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """签发 JWT。

    入参:
        subject: 放进 sub 的标识（用户名）
        extra: 额外声明（如 role）
    返回:
        HS256 编码的 token
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "iat": now, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并校验 JWT。

    异常:
        UnauthorizedError: 签名错误、过期、缺少 sub 等任意失效情形
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except InvalidTokenError as exc:
        raise UnauthorizedError("token 无效或已过期") from exc
    if not payload.get("sub"):
        raise UnauthorizedError("token 缺少 sub 声明")
    return payload



from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.errors import UnauthorizedError
from backend.crud.special import users as users_crud
from backend.db.session import get_db
from backend.db.models import User

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


def data_scope(user: User) -> int | None:
    """返回该账号的数据可见范围：None=全部，整数=仅该机构。

    商家账号（merchant）只能看自己绑定机构的数据；管理员与运营看全部。
    统一在这里判断，避免每个路由各写一遍、漏一个就形成越权。
    商家账号若没有绑定机构（历史数据），返回 -1 使其看不到任何业务数据，
    宁可空列表也不要越权。
    """
    if getattr(user, "role", None) == "merchant":
        return user.client_id if user.client_id is not None else -1
    return None
