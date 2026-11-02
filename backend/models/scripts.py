"""scripts：话术表（db_schema.md §1.3）。"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.config import ScriptStatus
from backend.db.base import Base, MYSQL_TABLE_ARGS

if TYPE_CHECKING:
    from backend.models.audits import Audit
    from backend.models.clients import Client


class Script(Base):
    """待审话术（CRUD 2）；client_id 外键 ON DELETE RESTRICT。"""

    __tablename__ = "scripts"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scene: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ScriptStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    client: Mapped["Client"] = relationship(
        back_populates="scripts", passive_deletes=True
    )
    audits: Mapped[list["Audit"]] = relationship(
        back_populates="script", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Script id={self.id} client_id={self.client_id} status={self.status}>"
