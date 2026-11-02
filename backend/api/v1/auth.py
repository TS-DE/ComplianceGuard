"""鉴权路由：register / login / me（api_spec.md §2）。"""

from fastapi import APIRouter, status

from backend.core.security import CurrentUser, DbSession
from backend.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenData,
    UserBrief,
    UserDetail,
)
from backend.schemas.common import ok
from backend.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_200_OK)
def register(payload: RegisterRequest, db: DbSession) -> dict:
    """注册账号；用户名重复返回 409。"""
    user = auth_service.register(
        db, payload.username, payload.password, payload.role.value
    )
    return ok(UserBrief.model_validate(user).model_dump())


@router.post("/login")
def login(payload: LoginRequest, db: DbSession) -> dict:
    """登录换取 access_token；失败统一 401。"""
    user = auth_service.authenticate(db, payload.username, payload.password)
    token = auth_service.issue_token(user)
    data = TokenData(
        access_token=token, user=UserBrief.model_validate(user)
    ).model_dump()
    return ok(data)


@router.get("/me")
def me(current_user: CurrentUser) -> dict:
    """当前登录用户信息（需 token）。"""
    return ok(UserDetail.model_validate(current_user).model_dump(mode="json"))
