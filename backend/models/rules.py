"""rules：规则库表（db_schema.md §1.5），Agent 工具读取。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.constants import DEFAULT_RULE_VERSION, RuleLevel
from backend.db.base import Base, MYSQL_TABLE_ARGS


class Rule(Base):
    """违规模式规则；改规则必须 version + 1 并存旧版（CLAUDE.md 铁律 7）。"""

    __tablename__ = "rules"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    axis: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    law_article: Mapped[str] = mapped_column(String(80), nullable=False)
    pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(
        Enum(RuleLevel, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    example_bad: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text(str(DEFAULT_RULE_VERSION))
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        # 库侧 ON UPDATE：绕过 ORM 直接改表时也会刷新
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Rule id={self.id} axis={self.axis} level={self.level} v{self.version}>"
