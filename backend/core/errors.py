"""统一业务异常与全局异常处理器。

约定：HTTP 状态码与返回体 code 保持一致（api_spec.md §1.1），
前端既可以看状态码，也可以只看 body.code，两者不会打架。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

CODE_BAD_REQUEST = 400
CODE_UNAUTHORIZED = 401
CODE_FORBIDDEN = 403
CODE_NOT_FOUND = 404
CODE_CONFLICT = 409
CODE_UNPROCESSABLE = 422
CODE_SERVER_ERROR = 500


class AppError(Exception):
    """业务异常基类：service/deps 层抛出，由全局处理器转成统一返回体。"""

    def __init__(self, code: int, msg: str, data: object = None) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.data = data


class NotFoundError(AppError):
    """资源不存在 -> 404。"""

    def __init__(self, resource: str, res_id: int) -> None:
        super().__init__(CODE_NOT_FOUND, f"{resource} {res_id} 不存在")


class ConflictError(AppError):
    """唯一键冲突 / 有下游引用 -> 409。"""

    def __init__(self, msg: str) -> None:
        super().__init__(CODE_CONFLICT, msg)


class UnauthorizedError(AppError):
    """未认证或 token 失效 -> 401。"""

    def __init__(self, msg: str = "未认证或登录已失效") -> None:
        super().__init__(CODE_UNAUTHORIZED, msg)


class BusinessValidationError(AppError):
    """业务校验失败（如 axis 不在枚举内）-> 422。"""

    def __init__(self, msg: str) -> None:
        super().__init__(CODE_UNPROCESSABLE, msg)


def _body(code: int, msg: str, data: object = None) -> JSONResponse:
    """拼装统一返回体，headers 由调用方按需追加。"""
    return JSONResponse(
        status_code=code,
        content={"code": code, "msg": msg, "data": data, "total": None},
    )


async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    resp = _body(exc.code, exc.msg, exc.data)
    if exc.code == CODE_UNAUTHORIZED:
        resp.headers["WWW-Authenticate"] = "Bearer"
    return resp


async def _http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    # FastAPI 自身抛的 401/404/405 等也走统一返回体
    return _body(exc.status_code, str(exc.detail))


async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic 参数校验失败按契约归为 400；只回字段位置与原因，不回原始输入
    errors = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    return _body(CODE_BAD_REQUEST, "参数校验失败", errors)


async def _integrity_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    # 兜底：service 层没提前拦住的外键/唯一键冲突
    logger.warning("数据库完整性冲突: %s", exc.orig)
    return _body(CODE_CONFLICT, "数据冲突（唯一键或外键约束）")


async def _db_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("数据库异常", exc_info=exc)
    return _body(CODE_SERVER_ERROR, "数据库异常")


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    # 不泄露堆栈给客户端，只写日志
    logger.exception("未处理异常", exc_info=exc)
    return _body(CODE_SERVER_ERROR, "服务异常")


def register_exception_handlers(app: FastAPI) -> None:
    """把所有处理器挂到 app 上；顺序无关，FastAPI 按异常类型 MRO 匹配。"""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(IntegrityError, _integrity_handler)
    app.add_exception_handler(SQLAlchemyError, _db_error_handler)
    app.add_exception_handler(Exception, _unhandled_handler)



class ModelCallError(RuntimeError):
    """脱敏的模型边界错误，kind及attempt_limit驱动重试而非解析消息。"""
    def __init__(self, message, kind='connection', attempt_limit=3):
        super().__init__(message)
        self.kind=kind
        self.attempt_limit=attempt_limit


def model_error(exc, timeout, service='聊天服务'):
    """保留HTTP码但不回显URL、reason原文、密钥、响应或用户文本。"""
    from urllib.error import HTTPError, URLError
    if isinstance(exc,ModelCallError): return exc
    # OpenAI/LangChain SDK 抛的不是 urllib 异常：不认这些类型的话，4xx 会被当成
    # "网络错误重试三次"，两个后端的重试语义就不等价，"换后端结果一致"这条验收也没法成立。
    # 刻意用鸭子类型而不是 import openai：默认后端是 urllib，异常层不该绑住可选依赖。
    status = getattr(exc, 'status_code', None)
    if isinstance(status, int):
        return ModelCallError(f'{service} HTTP {status}','http',2 if status>=500 else 1)
    if type(exc).__name__ in ('APITimeoutError','APIConnectionError','ConnectTimeout','ReadTimeout'):
        return ModelCallError(f'{service}连接或读超时（{timeout}s）','timeout',2)
    if isinstance(exc,HTTPError):
        return ModelCallError(f'{service} HTTP {exc.code}','http',2 if exc.code>=500 else 1)
    if isinstance(exc,TimeoutError) or (isinstance(exc,URLError) and isinstance(exc.reason,TimeoutError)):
        return ModelCallError(f'{service}读超时（{timeout}s）','timeout',2)
    if isinstance(exc,ValueError):
        return ModelCallError('聊天响应非合法 JSON','invalid_json',1)
    if isinstance(exc,URLError):
        return ModelCallError(f'{service}连接失败（原因已脱敏）','connection',3)
    return ModelCallError(f'{service}网络错误','network',3)
