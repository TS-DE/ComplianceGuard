"""v1 路由聚合：认证、资源及 AI 操作。"""
from fastapi import APIRouter
from backend.api.v1 import ai, auth, resources

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(resources.router)
api_router.include_router(ai.router)
