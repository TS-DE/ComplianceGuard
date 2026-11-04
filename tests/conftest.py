"""pytest 公共夹具：独立测试库 + 事务级清理 + 认证客户端。

铁律：测试不碰业务库。库名由 TEST_DATABASE_URL 指定，
缺省为业务库名加 _test 后缀，create_all 自建、跑完不删（便于排查残留）。
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# 必须在 import backend.* 之前设置：config 是 lru_cache 的模块级单例，
# 先设 TEST_* 才能保证 session.py 用的是测试库。
os.environ["BCRYPT_ROUNDS"] = "4"  # 测试加速，与生产成本因子无关
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")


def _resolve_test_dsn() -> str:
    """推导测试库 DSN：优先 TEST_DATABASE_URL，否则业务库名后加 _test。"""
    if TEST_DB_URL:
        return TEST_DB_URL
    from urllib.parse import urlparse

    from backend.core.config import settings

    parsed = urlparse(settings.database_url)
    base = parsed.path.lstrip("/")
    return parsed._replace(path=f"/{base}_test").geturl()


def _create_test_database(dsn: str) -> None:
    """建测试库（IF NOT EXISTS），不触碰业务库。"""
    from urllib.parse import urlparse

    parsed = urlparse(dsn)
    db_name = parsed.path.lstrip("/")
    server = parsed._replace(path="/").geturl()
    engine = create_engine(server, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
    engine.dispose()


@pytest.fixture(scope="session")
def test_dsn() -> str:
    """会话级：确保测试库存在并建表。"""
    dsn = _resolve_test_dsn()
    from sqlalchemy import inspect
    from sqlalchemy.engine import make_url
    from backend.core.config import settings
    # 必须先拦截误配，再做建库、建表或测试迁移。
    if make_url(dsn).database == make_url(settings.database_url).database:
        raise RuntimeError("测试数据库不得与业务数据库相同")
    _create_test_database(dsn)
    engine = create_engine(dsn, future=True)
    from backend.db.models import Base

    Base.metadata.create_all(bind=engine)
    # create_all 不补旧表列；仅迁移独立测试库，不接触生产库。
    columns = {column["name"] for column in inspect(engine).get_columns("rules")}
    with engine.begin() as conn:
        if "detector" not in columns:
            conn.execute(text("ALTER TABLE rules ADD COLUMN detector "
                              "ENUM('keyword','regex','semantic','llm_judge') "
                              "NOT NULL DEFAULT 'llm_judge'"))
        if "exemptions" not in columns:
            conn.execute(text("ALTER TABLE rules ADD COLUMN exemptions JSON NULL"))
    from scripts.migrate_audits_cost_nullable import migrate
    migrate(engine, apply=True)
    from scripts.migrate_scripts_redteam import migrate as migrate_redteam
    migrate_redteam(engine, apply=True)
    # users 的多租户字段与 merchant 角色：create_all 不会给已存在的表补列，
    # 老测试库因此缺 users.client_id，会让所有登录相关用例 500。
    from scripts.migrate_users_tenant import migrate as migrate_tenant
    migrate_tenant(engine, apply=True)
    engine.dispose()
    yield dsn


@pytest.fixture(scope="session")
def app_with_test_db(test_dsn: str):
    """把 backend 的 engine/Session 指向测试库，并产出 app。"""
    import backend.db.session as db_session

    engine = create_engine(test_dsn, future=True)
    db_session.engine = engine
    db_session.SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    # 路由里的 DbSession 依赖引用的是函数对象，get_db 内部取 SessionLocal 已是新的
    from backend.main import app

    yield app


@pytest.fixture()
def db(app_with_test_db) -> Generator[Session, None, None]:
    """每个用例一个 Session。"""
    from backend.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_tables(app_with_test_db) -> Generator[None, None, None]:
    """每个用例前清空业务表（顺序遵守外键），保证用例互不影响。"""
    from backend.db.session import SessionLocal

    session = SessionLocal()
    try:
        for table in ("audits", "scripts", "clients", "rules", "users"):
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
    finally:
        session.close()
    yield


@pytest.fixture()
def client(app_with_test_db) -> TestClient:
    """未认证客户端。"""
    return TestClient(app_with_test_db)


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    """注册并登录一个测试账号，返回带 Bearer 的头。"""
    credentials = {"username": "pytest_user", "password": "pytest_pass"}
    client.post("/api/v1/auth/register", json=credentials)
    resp = client.post("/api/v1/auth/login", json=credentials)
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
