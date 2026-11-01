"""v1 路由聚合：新模块在此登记，main.py 只挂这一个 router。"""

from fastapi import APIRouter

from backend.api.v1 import auth

api_router = APIRouter()
api_router.include_router(auth.router)
