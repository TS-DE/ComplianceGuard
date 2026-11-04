"""v1 路由聚合：认证、四套同构 CRUD、AI 能力、素材摄取。

这里曾经是两套并存的聚合入口（另有一份 `api/v1/router/__init__.py`，
2026-11-02 一次并发改动留下的结构漂移，CLAUDE.md §7.11 记过这个坑）。
本文件是唯一入口，`router/` 子包已删除——两个聚合点意味着改路由的人只注册一半。
"""

from fastapi import APIRouter

from backend.api.v1 import ai, auth, ingest, resources

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(resources.router)
api_router.include_router(ingest.router)
api_router.include_router(ai.router)
