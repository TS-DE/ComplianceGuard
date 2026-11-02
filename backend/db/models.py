"""五张业务表的 ORM 映射；保持既有数据库结构不变。"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, Enum, func, text
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.config import SCORE_COMPLIANT, SCORE_INCOMPLETE, DEFAULT_INDUSTRY, DEFAULT_PLAN, DEFAULT_RULE_VERSION, RuleLevel, ScriptStatus, UserRole
from backend.db.base import Base, MYSQL_TABLE_ARGS
COST_PRECISION = 10
COST_SCALE = 6

class User(Base):
    """登录账号；密码只存 bcrypt 哈希，禁止明文。"""

    __tablename__ = "users"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # ENUM 用 native_enum 默认行为即可，MySQL 侧生成 ENUM('admin','operator')
    role: Mapped[str] = mapped_column(
        Enum(UserRole, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'operator'"),
    )
    # TINYINT(1)：MySQL 里 Boolean 会生成为 TINYINT(1)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"

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
