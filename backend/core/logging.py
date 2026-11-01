"""日志初始化：统一格式，替代 print 调试。"""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(debug: bool = False) -> None:
    """配置根 logger；重复调用安全（basicConfig 已配置时不会叠加 handler）。"""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=LOG_FORMAT,
    )
