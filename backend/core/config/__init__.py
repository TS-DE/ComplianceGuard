"""应用配置：唯一来源是 .env，代码里禁止硬编码密钥与 DSN。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def cors_origin_list(self) -> list[str]:
        """把 CORS_ORIGINS 拆成列表，忽略空白项。"""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程内缓存配置实例，避免每次请求重复解析 .env。"""
    return Settings()


settings = get_settings()



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
