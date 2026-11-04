"""应用配置：唯一来源是 .env，代码里禁止硬编码密钥与 DSN。"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/core/config/__init__.py → 上三级是项目根（data/ 与 .env 都在这里）
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """全局配置项。字段与 .env / .env.example 一一对应。

    没有默认值的字段（database_url、jwt_secret）必须由 .env 提供；
    缺失时启动即失败，好过带着空密钥跑起来。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    app_name: str = "ComplianceGuard"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # ---- 数据库 ----
    database_url: str = Field(
        ...,
        description="MySQL DSN：mysql+pymysql://user:pwd@host:port/db?charset=utf8mb4",
    )
    db_echo: bool = False

    # ---- JWT ----
    jwt_secret: str = Field(..., min_length=16, description="HS256 签名密钥，只存 .env")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # ---- CORS（逗号分隔字符串，避免 list 型环境变量要写 JSON）----
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- 安全 ----
    bcrypt_rounds: int = 12

    # ---- 文档解析（商家素材摄取）----
    # 相对路径一律相对项目根解析；写绝对路径也行（换机器部署时只改 .env）。
    upload_dir: str = "data/uploads"
    # 模型权重刻意放项目盘：默认会写进 C:\Users\<user>\.cache，而 C 盘只剩几 GB。
    model_dir: str = "data/models"
    parse_ocr_enabled: bool = True
    parse_asr_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        """把 CORS_ORIGINS 拆成列表，忽略空白项。"""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @staticmethod
    def resolve_path(value: str) -> "Path":
        """相对路径挂到项目根下，绝对路径原样使用。"""
        candidate = Path(value)
        return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate

    @property
    def upload_path(self) -> "Path":
        return self.resolve_path(self.upload_dir)

    @property
    def model_path(self) -> "Path":
        return self.resolve_path(self.model_dir)


def configure_model_cache() -> None:
    """把各家模型缓存目录指到项目盘，必须在任何会下载模型的库被导入前调用。

    不这么做的话：onnxruntime/modelscope/transformers 会把几百 MB 权重写进
    C:\\Users\\<user>\\.cache 与 .modelscope，而本机 C 盘只剩 2 GB——
    表现是"下载中途磁盘满、报错还看不出为什么"。
    """
    root = get_settings().model_path
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MODELSCOPE_CACHE", str(root / "modelscope"))
    os.environ.setdefault("HF_HOME", str(root / "huggingface"))
    os.environ.setdefault("TORCH_HOME", str(root / "torch"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程内缓存配置实例，避免每次请求重复解析 .env。"""
    return Settings()


settings = get_settings()

# 导入即生效：任何下游模块再 import modelscope/transformers 时缓存路径已经指到项目盘。
configure_model_cache()



import logging

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(debug: bool = False) -> None:
    """配置根 logger；重复调用安全（basicConfig 已配置时不会叠加 handler）。"""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=LOG_FORMAT,
    )


from enum import Enum

# ---------------------------------------------------------------- 分数档位
SCORE_COMPLIANT = 2
SCORE_MINOR = 1
SCORE_VIOLATION = 0
SCORE_INCOMPLETE = -1
VALID_SCORES: tuple[int, ...] = (
    SCORE_COMPLIANT,
    SCORE_MINOR,
    SCORE_VIOLATION,
    SCORE_INCOMPLETE,
)
SCORE_LABELS: dict[int, str] = {
    SCORE_COMPLIANT: "合规",
    SCORE_MINOR: "轻微风险",
    SCORE_VIOLATION: "违规",
    SCORE_INCOMPLETE: "判定未完成（待人工复核）",
}

# ---------------------------------------------------------------- 规则等级
class RuleLevel(str, Enum):
    """规则等级：hard 一票否决，soft 需要累计。"""

    HARD = "hard"
    SOFT = "soft"


# ---------------------------------------------------------------- 规则轴
class RuleAxis(str, Enum):
    """8 条语义轴（db_schema.md §3），是起点不是终点。"""

    ABSOLUTE_TERMS = "absolute_terms"
    EFFICACY_CLAIM = "efficacy_claim"
    SAFETY_GUARANTEE = "safety_guarantee"
    DISEASE_TREATMENT = "disease_treatment"
    FALSE_QUANTIFY = "false_quantify"
    BEFORE_AFTER = "before_after"
    INDUCEMENT = "inducement"
    FALSE_AUTHORITY = "false_authority"


AXIS_LABELS: dict[str, str] = {
    RuleAxis.ABSOLUTE_TERMS.value: "绝对化用语",
    RuleAxis.EFFICACY_CLAIM.value: "功效断言/保证",
    RuleAxis.SAFETY_GUARANTEE.value: "安全性保证",
    RuleAxis.DISEASE_TREATMENT.value: "疾病治疗功能暗示",
    RuleAxis.FALSE_QUANTIFY.value: "无法验证的量化承诺",
    RuleAxis.BEFORE_AFTER.value: "术前术后对比",
    RuleAxis.INDUCEMENT.value: "焦虑式诱导",
    RuleAxis.FALSE_AUTHORITY.value: "虚构权威背书",
}

# 各轴默认等级（db_schema.md §3 表），建规则时若未指定 level 用它兜底
AXIS_DEFAULT_LEVEL: dict[str, str] = {
    RuleAxis.ABSOLUTE_TERMS.value: RuleLevel.HARD.value,
    RuleAxis.EFFICACY_CLAIM.value: RuleLevel.HARD.value,
    RuleAxis.SAFETY_GUARANTEE.value: RuleLevel.HARD.value,
    RuleAxis.DISEASE_TREATMENT.value: RuleLevel.HARD.value,
    RuleAxis.FALSE_QUANTIFY.value: RuleLevel.HARD.value,
    RuleAxis.BEFORE_AFTER.value: RuleLevel.SOFT.value,
    RuleAxis.INDUCEMENT.value: RuleLevel.SOFT.value,
    RuleAxis.FALSE_AUTHORITY.value: RuleLevel.SOFT.value,
}

# ---------------------------------------------------------------- 其它枚举
class UserRole(str, Enum):
    """账号角色；D1 只做区分，不做细粒度授权。"""

    ADMIN = "admin"
    OPERATOR = "operator"
    # 商家：自助上传与查看自己机构的审查结果，看不到平台级规则与压测
    MERCHANT = "merchant"


class ScriptStatus(str, Enum):
    """话术状态流转：pending -> audited -> archived。"""

    PENDING = "pending"
    AUDITED = "audited"
    ARCHIVED = "archived"


DEFAULT_INDUSTRY = "medical_beauty"
DEFAULT_PLAN = "free"
DEFAULT_RULE_VERSION = 1

# ---------------------------------------------------------------- 分页
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ---------------------------------------------------------------- 文案
DISCLAIMER_TEXT = (
    "本系统输出为合规风险辅助提示，不构成法律意见，"
    "也不能替代《医疗广告审查证明》的行政前置审查。"
)
