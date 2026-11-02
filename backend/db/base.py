"""ORM 声明基类：所有模型继承 Base，建表元数据集中在 Base.metadata。"""

from sqlalchemy.orm import DeclarativeBase

# 所有表统一的 MySQL 建表选项（db_schema.md §1.6）
MYSQL_TABLE_ARGS: dict[str, str] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类。"""
