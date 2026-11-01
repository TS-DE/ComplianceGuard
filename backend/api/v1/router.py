"""v1 路由聚合：新模块在此登记，main.py 只挂这一个 router。"""

from fastapi import APIRouter

from backend.api.v1 import audits, auth, clients, rules, scripts

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(clients.router)
api_router.include_router(scripts.router)
api_router.include_router(audits.router)
api_router.include_router(rules.router)
