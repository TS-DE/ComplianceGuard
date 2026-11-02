"""建库建表脚本。

默认只打印 DDL 预览（铁律：破坏性/结构性变更必须先预览）；
加 --apply 才真正执行 CREATE DATABASE / CREATE TABLE。
表若已存在只跳过，不 DROP、不 TRUNCATE。

用法：
    python -m scripts.init_db           # 打印 DDL 预览
    python -m scripts.init_db --apply   # 实际建库建表
"""

import argparse
import logging
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.core.config import settings
from backend.db.models import Base

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def emit(line: str = "") -> None:
    """面向人的报告输出（非调试），写 stdout；仅 ASCII/中文，不含 emoji。"""
    sys.stdout.write(line + "\n")
logger = logging.getLogger("init_db")

# 库名与字符集：与 db_schema.md §1 一致
DB_CHARSET = "utf8mb4"
DB_COLLATE = "utf8mb4_unicode_ci"


def _split_dsn(dsn: str) -> tuple[str, str, str]:
    """从 DSN 拆出 server_dsn（不带库名）、库名、完整 DSN。"""
    parsed = urlparse(dsn)
    db_name = parsed.path.lstrip("/")
    if not db_name:
        raise SystemExit("DSN 缺少库名，请检查 .env 的 DATABASE_URL")
    server_dsn = parsed._replace(path="/").geturl()
    return server_dsn, db_name, dsn


def _create_database(server_dsn: str, db_name: str) -> None:
    """建库（IF NOT EXISTS）；不删任何已存在的库。"""
    engine = create_engine(server_dsn, future=True)
    stmt = (
        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
        f"DEFAULT CHARACTER SET {DB_CHARSET} COLLATE {DB_COLLATE}"
    )
    with engine.begin() as conn:
        conn.execute(text(stmt))
    engine.dispose()
    logger.info("数据库就绪: %s", db_name)


def _table_ddl() -> list[tuple[str, str, list[str]]]:
    """生成 (表名, CREATE TABLE IF NOT EXISTS, [CREATE INDEX...])，按外键依赖排序。

    预览与 --apply 共用这份语句，保证"看到的就是执行的"。
    注意：MySQL 8 不支持 CREATE INDEX IF NOT EXISTS，索引的幂等靠反射检查兜底。
    """
    dialect = mysql.dialect()
    out = []
    for table in Base.metadata.sorted_tables:
        create_sql = str(
            CreateTable(table, if_not_exists=True).compile(dialect=dialect)
        ).strip()
        index_sqls = [
            str(CreateIndex(index).compile(dialect=dialect)).strip()
            for index in sorted(table.indexes, key=lambda i: i.name or "")
        ]
        out.append((table.name, create_sql, index_sqls))
    return out


def _print_ddl(db_name: str) -> None:
    """把完整 DDL 打到 stdout，供人工确认。"""
    emit("=" * 72)
    emit(f"DDL 预览：库 `{db_name}`")
    emit("=" * 72)
    emit(
        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
        f"DEFAULT CHARACTER SET {DB_CHARSET} COLLATE {DB_COLLATE};"
    )
    for _, create_sql, index_sqls in _table_ddl():
        emit("-" * 72)
        emit(create_sql.rstrip() + ";")
        for index_sql in index_sqls:
            emit(index_sql + ";  -- 仅在该表本次新建时执行")
    emit("=" * 72)
    emit("以上不含 DROP / TRUNCATE / ALTER 删列；已存在的表与索引会被跳过。")
    emit("确认无误后执行：python -m scripts.init_db --apply")


def _apply(dsn: str) -> list[str]:
    """逐表执行幂等 DDL，返回本次新建的表名列表。

    双保险：①语句本身带 IF NOT EXISTS ②执行前反射已有表，已存在则跳过索引创建。
    """
    engine = create_engine(dsn, future=True)
    created: list[str] = []
    with engine.begin() as conn:
        existing = set(inspect(conn).get_table_names())
        for name, create_sql, index_sqls in _table_ddl():
            conn.execute(text(create_sql))
            if name in existing:
                logger.info("跳过已存在的表: %s", name)
                continue
            for index_sql in index_sqls:
                conn.execute(text(index_sql))
            created.append(name)
            logger.info("新建表: %s（索引 %d 个）", name, len(index_sqls))
    engine.dispose()
    logger.info("建表完成，新建 %d 张: %s", len(created), created or "无（均已存在）")
    return created


def main(argv: list[str] | None = None) -> int:
    """入口：无 --apply 时只预览。"""
    parser = argparse.ArgumentParser(description="ComplianceGuard 建库建表")
    parser.add_argument("--apply", action="store_true", help="真正执行建库建表")
    args = parser.parse_args(argv)

    server_dsn, db_name, dsn = _split_dsn(settings.database_url)
    if not args.apply:
        _print_ddl(db_name)
        return 0

    _create_database(server_dsn, db_name)
    _apply(dsn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
