"""clients：机构表（db_schema.md §1.2）。"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.constants import DEFAULT_INDUSTRY, DEFAULT_PLAN
from backend.db.base import Base, MYSQL_TABLE_ARGS

if TYPE_CHECKING:  # 仅类型检查时导入，避免与 scripts 模型循环引用
    from backend.models.scripts import Script


class Client(Base):
    """机构（CRUD 1）；industry 为多切片预留。"""

    __tablename__ = "clients"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    industry: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text(f"'{DEFAULT_INDUSTRY}'")
    )
    contact: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text(f"'{DEFAULT_PLAN}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    # passive_deletes=True：删除交给数据库 RESTRICT 约束，ORM 不抢先置 NULL
    scripts: Mapped[list["Script"]] = relationship(
        back_populates="client", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name}>"
