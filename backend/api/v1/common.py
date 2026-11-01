"""路由层共用依赖：分页参数。"""

from typing import Annotated

from fastapi import Depends, Query

from backend.core.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from backend.schemas.common import PageParams


def page_params(
    page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    """把 query 里的 page/page_size 收拢成一个对象，越界走 400。"""
    return PageParams(page=page, page_size=page_size)


Page = Annotated[PageParams, Depends(page_params)]
