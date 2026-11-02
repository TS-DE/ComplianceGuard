"""v1 路由聚合：鉴权与同构资源。"""
from fastapi import APIRouter
from backend.api.v1 import auth, resources

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(resources.router)
