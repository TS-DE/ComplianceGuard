"""audits：审查记录表（db_schema.md §1.4），D3 Agent 落库目标。"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.constants import SCORE_COMPLIANT, SCORE_INCOMPLETE
from backend.db.base import Base, MYSQL_TABLE_ARGS

if TYPE_CHECKING:
    from backend.models.scripts import Script

# DECIMAL(10,6)：成本精确到微元，用 Numeric 而非 Float 避免浮点误差
COST_PRECISION = 10
COST_SCALE = 6


class Audit(Base):
    """一次审查结果（CRUD 3）；score 只能是 2/1/0/-1。"""

    __tablename__ = "audits"
    # 分数取值域交给数据库强制（-1 未完成 ~ 2 合规），绕过 ORM 写库也拦得住
    __table_args__ = (
        CheckConstraint(
            f"score BETWEEN {SCORE_INCOMPLETE} AND {SCORE_COMPLIANT}",
            name="ck_audits_score",
        ),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scripts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # TINYINT 有符号（-128~127）：能存 -1（未完成）；非 MySQL 方言退化为 SMALLINT
    score: Mapped[int] = mapped_column(
        SmallInteger().with_variant(TINYINT(), "mysql"), nullable=False
    )
    hit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    hits_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    law_refs_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    rewritten_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewrite_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost: Mapped[Decimal] = mapped_column(
        Numeric(COST_PRECISION, COST_SCALE), nullable=False, server_default=text("0")
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    # 1 = 有轴调用失败，报告里不许当合规
    incomplete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True
    )

    script: Mapped["Script"] = relationship(
        back_populates="audits", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Audit id={self.id} script_id={self.script_id} score={self.score}>"
