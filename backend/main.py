"""FastAPI 入口：挂中间件、异常处理器与 v1 路由。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.router import api_router
from backend.core.config import settings
from backend.core.constants import DISCLAIMER_TEXT
from backend.core.errors import register_exception_handlers
from backend.core.logging import setup_logging
from backend.schemas.common import ok


def create_app() -> FastAPI:
    """应用工厂：测试与 uvicorn 共用同一构造路径。"""
    setup_logging(settings.debug)
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DISCLAIMER_TEXT,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    @app.get("/health", tags=["health"])
    def health() -> dict:
        """存活探针：不查库、不鉴权。"""
        return ok({"status": "ok", "version": settings.app_version})

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
