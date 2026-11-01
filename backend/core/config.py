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
