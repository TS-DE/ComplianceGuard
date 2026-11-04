"""六张业务表的 ORM 映射：users/clients/sources/scripts/audits/rules。"""

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
    # 商家账号绑定到具体机构；平台管理员为 NULL（可看全部）
    client_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
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

class Source(Base):
    """商家上传的原始素材（海报 / 扫描件 / 录音 / 文档）；一条素材切出 N 条话术。

    为什么单独成表而不是在 scripts 上记个文件名：一份 PDF 会切成几十条话术，
    而"哪个文件、什么引擎、第几页、置信度多少、警告"是**素材的属性**，
    复制到每条话术上既冗余又改不动（重跑一次 OCR 要更新几十行）。
    审查结论要回溯"这句是哪来的"，靠 scripts.source_id → sources 一次 JOIN 就够。
    """

    __tablename__ = "sources"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # 解析结果形态：text/sheet/docx/slides/pdf_text/pdf_scan/image/audio
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # 实际干了活的库：decode/python-docx/openpyxl·xlrd/python-pptx/pdfplumber
    # /pdfplumber+rapidocr/rapidocr/funasr:sensevoice-small
    engine: Mapped[str] = mapped_column(String(40), nullable=False)
    # 内容指纹：同一张海报重复上传要能看出来，否则统计口径会被同一份素材灌水
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # 相对项目根的存储路径；NULL 表示本轮只解析预览、没有落盘
    stored_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 页码/段落/毫秒等结构化信息：{pages, slides, sheets, seconds, blocks, chars}
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # OCR/ASR 平均置信度；纯文本层为 NULL（意为"不存在识别误差"，不是"0"）
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    parse_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    client: Mapped["Client"] = relationship(passive_deletes=True)
    # 反向名是 source_obj 而不是 source：Script 已有一个叫 source 的列（manual/redteam），
    # SQLAlchemy 不允许同名关系与列并存，硬要同名会在建映射时直接报错。
    scripts: Mapped[list["Script"]] = relationship(
        back_populates="source_obj", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Source id={self.id} filename={self.filename} kind={self.kind}>"

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
    # source 说"这条记录是谁产生的"（人工录入 / 红队生成）；
    # 至于"人工录入的那份文件是什么"，由下面的 source_id 指向 sources。
    # 两个字段刻意不合并：合并后红队样本没地方放，商家素材也没地方查。
    source: Mapped[str] = mapped_column(Enum("manual", "redteam"), nullable=False, server_default=text("'manual'"))
    redteam_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # ---- 素材溯源：这句话来自哪份文件的哪个位置（无素材来源时全为 NULL）----
    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # pos 给机器（排序、按页统计），ref 给人（"第3页" / "Sheet1·第12行" / "语音第4句"）
    source_pos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # OCR/ASR 单块置信度；NULL 表示来自文本层，不存在识别误差
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
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
    source_obj: Mapped["Source | None"] = relationship(
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
    cost: Mapped[Decimal | None] = mapped_column(
        Numeric(COST_PRECISION, COST_SCALE).evaluates_none(), nullable=True, server_default=text("NULL")
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
    detector: Mapped[str] = mapped_column(
        Enum("keyword", "regex", "semantic", "llm_judge"),
        nullable=False, server_default=text("'llm_judge'"),
    )
    exemptions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
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
