"""通用响应体与分页参数（api_spec.md §1.1 / §1.3）。"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from backend.core.config import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

T = TypeVar("T")

CODE_OK = 200
MSG_OK = "ok"


class ApiResponse(BaseModel, Generic[T]):
    """统一返回体 {code, msg, data, total}。"""

    code: int = CODE_OK
    msg: str = MSG_OK
    data: T | None = None
    total: int | None = None


class PageParams(BaseModel):
    """分页参数；page_size 上限由常量控制。"""

    page: int = Field(DEFAULT_PAGE, ge=1)
    page_size: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def ok(data: Any = None, total: int | None = None, msg: str = MSG_OK) -> dict[str, Any]:
    """构造成功返回体，路由层统一用它，避免手拼字典。"""
    return {"code": CODE_OK, "msg": msg, "data": data, "total": total}
