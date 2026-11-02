"""核对表结构：打印 SHOW TABLES 与每张表的列定义。

用途：建库后自检、以及与 db_schema.md 对账。只读，不做任何变更。
"""

import logging
import sys

from sqlalchemy import create_engine, text

from backend.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def emit(line: str = "") -> None:
    """面向人的报告输出（非调试），写 stdout；仅 ASCII/中文，不含 emoji。"""
    sys.stdout.write(line + "\n")


def main() -> int:
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as conn:
        tables = [row[0] for row in conn.execute(text("SHOW TABLES")).fetchall()]
        emit("SHOW TABLES:")
        for name in tables:
            emit(f"  - {name}")
        for name in tables:
            emit("-" * 72)
            emit(f"DESCRIBE {name}:")
            for row in conn.execute(text(f"DESCRIBE `{name}`")).fetchall():
                emit(f"  {row[0]:<18} {row[1]:<16} null={row[2]:<4} key={row[3]:<4} {row[4] or ''}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
