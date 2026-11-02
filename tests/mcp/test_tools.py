"""MCP 工具隔离测试：不连接业务库，不调用外部模型。"""

import asyncio
import importlib.util
import json
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def clean_tables():
    """覆盖根目录的 MySQL 自动清理，避免离线测试访问业务数据。"""
    yield


def test_exact_registration_and_offline_selftest():
    assert importlib.util.find_spec("backend.mcp_server.server") is not None
    from backend.mcp_server import server

    tools = asyncio.run(server.mcp.list_tools())
    expected = {
        "rag_search_law": ["query", "top_k"],
        "db_query_rules": ["axis"],
        "db_query_violation_history": ["client_id", "limit"],
        "db_query_scenes": [],
        "db_save_redteam_result": ["run_id", "sample", "judge", "category"],
        "audit_recheck": ["text", "client_id"],
    }
    assert {t.name: list(t.inputSchema["properties"]) for t in tools} == expected
    result = subprocess.run(
        [sys.executable, "-m", "backend.mcp_server.server", "--selftest"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    listing = json.loads(result.stdout)
    assert {t["name"] for t in listing} == set(expected)
    assert all("inputSchema" in t for t in listing)


def test_rag_reuses_retriever_and_recheck_is_pending(monkeypatch):
    from dataclasses import make_dataclass
    from types import ModuleType
    from backend.mcp_server import server

    module = ModuleType("backend.rag.retrieve")
    hit = make_dataclass("Hit", ["text", "code", "source", "score", "route", "parent_text", "doc_type"])
    module.CANDIDATE_K = 10
    calls = []

    def search(query, top_k=3):
        calls.append((query, top_k))
        return [hit("条文", "第16条", "广告法", 0.8, "bm25;degraded=vector_unavailable", "完整条文", "law")]

    module.search = search
    monkeypatch.setitem(sys.modules, "backend.rag.retrieve", module)
    assert server.rag_search_law("安全", 2) == [
        {"text": "条文", "code": "第16条", "source": "广告法", "score": 0.8,
         "route": "bm25;degraded=vector_unavailable", "parent_text": "完整条文", "doc_type": "law"}
    ]
    assert calls == [("安全", 2)]
    assert server.audit_recheck("原文", 1) == {"ok": False, "reason": "pending_d3"}


@pytest.mark.parametrize("name,args", [
    ("rag_search_law", (" ",)), ("rag_search_law", ("x", 0)),
    ("rag_search_law", ("x", 101)), ("rag_search_law", ("x", True)),
    ("audit_recheck", ("", 1)), ("audit_recheck", ("x", 0)),
])
def test_rag_and_recheck_reject_invalid_inputs(name, args):
    from backend.mcp_server import server
    with pytest.raises(ValueError):
        getattr(server, name)(*args)


@pytest.fixture()
def tool_db(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from backend.db import session

    engine = create_engine("sqlite://")
    statements = [
        "CREATE TABLE rules (id INTEGER PRIMARY KEY, axis TEXT, law_article TEXT, "
        "pattern TEXT, level TEXT, version INTEGER, enabled BOOLEAN)",
        "CREATE TABLE scripts (id INTEGER PRIMARY KEY, client_id INTEGER, scene TEXT, content TEXT)",
        "CREATE TABLE audits (id INTEGER PRIMARY KEY, script_id INTEGER, score INTEGER, "
        "hits_json JSON, created_at DATETIME, incomplete BOOLEAN)",
        "INSERT INTO rules VALUES (1,'efficacy_claim','第16条','保证','hard',1,1),"
        "(2,'absolute_terms','第9条','最佳','hard',1,0)",
        "INSERT INTO scripts VALUES (1,1,'美白','样本甲'),(2,2,'美白','样本乙'),"
        "(3,1,NULL,'无场景'),(4,1,'','空场景'),(5,1,'美白','样本甲')",
        "INSERT INTO audits VALUES (1,1,0,'[]','2026-01-01',0),"
        "(2,1,1,'[]','2026-01-02',0),(3,1,2,'[]','2026-01-03',0),"
        "(4,1,-1,'[]','2026-01-04',1),(5,2,0,'[]','2026-01-05',0),"
        "(6,1,0,'[]','2026-01-06',1)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    monkeypatch.setattr(session, "SessionLocal", sessionmaker(bind=engine))
    yield engine
    engine.dispose()


def test_rules_read_only_enabled_filter_and_explicit_old_schema(tool_db):
    from backend.mcp_server import server
    from sqlalchemy import inspect

    rows = server.db_query_rules("efficacy_claim")
    assert len(rows) == 1
    assert rows[0]["pattern"] == "保证"
    assert rows[0]["detector"] is None and rows[0]["exemptions"] is None
    assert rows[0]["schema_status"] == "missing_columns"
    assert rows[0]["missing_columns"] == ["detector", "exemptions"]
    assert len(server.db_query_rules()) == 1
    assert server.db_query_rules("unmatched") == []
    assert "detector" not in {c["name"] for c in inspect(tool_db).get_columns("rules")}


def test_rules_reflect_optional_existing_columns(tool_db):
    from backend.mcp_server import server
    from sqlalchemy import text

    with tool_db.begin() as connection:
        connection.execute(text("ALTER TABLE rules ADD COLUMN detector TEXT"))
        connection.execute(text("ALTER TABLE rules ADD COLUMN exemptions JSON"))
        connection.execute(text("UPDATE rules SET detector='regex', exemptions='[]'"))
    row = server.db_query_rules()[0]
    assert row["detector"] == "regex" and row["exemptions"] == []
    assert row["schema_status"] == "complete" and row["missing_columns"] == []


def test_history_filters_client_complete_violations_and_limits(tool_db):
    from backend.mcp_server import server

    rows = server.db_query_violation_history(1)
    assert [r["score"] for r in rows] == [1, 0]
    assert all(r["script_id"] == 1 and r["hits"] == [] for r in rows)
    assert rows[0]["created_at"].startswith("2026-01-02")
    assert len(server.db_query_violation_history(1, 1)) == 1
    assert server.db_query_violation_history(99) == []


def test_scenes_are_distinct_with_bounded_samples(tool_db):
    from backend.mcp_server import server
    assert server.db_query_scenes() == [{"scene": "美白", "sample_scripts": ["样本甲", "样本乙"]}]


@pytest.mark.parametrize("name,args", [
    ("db_query_rules", (" ",)), ("db_query_rules", (1,)),
    ("db_query_violation_history", (0,)), ("db_query_violation_history", (True,)),
    ("db_query_violation_history", (1, 0)), ("db_query_violation_history", (1, 101)),
])
def test_database_validation_before_connection(name, args):
    from backend.mcp_server import server
    with pytest.raises(ValueError):
        getattr(server, name)(*args)


def test_redteam_durable_append_and_failure(monkeypatch, tmp_path):
    from backend.mcp_server import server
    from backend.tools import db_tool

    path = tmp_path / "internal" / "results.jsonl"
    monkeypatch.setattr(db_tool, "REDTEAM_PATH", path)
    for sample in ("样本甲", "样本乙"):
        assert server.db_save_redteam_result("run/1", sample, {"score": 0}, "功效") == {"ok": True}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["sample"] for r in rows] == ["样本甲", "样本乙"]
    assert rows[0] == {"run_id": "run/1", "sample": "样本甲", "judge": {"score": 0}, "category": "功效"}
    monkeypatch.setattr(db_tool, "REDTEAM_PATH", tmp_path)
    with pytest.raises(OSError):
        server.db_save_redteam_result("run", "样本", {}, "功效")


@pytest.mark.parametrize("args", [
    ("", "sample", {}, "category"), ("run", " ", {}, "category"),
    ("run", "sample", "not a dict", "category"), ("run", "sample", {}, ""),
    ("run", "sample", {"bad": float("nan")}, "category"),
])
def test_redteam_invalid_inputs_do_not_create_file(args, monkeypatch, tmp_path):
    from backend.mcp_server import server
    from backend.tools import db_tool
    path = tmp_path / "never-created.jsonl"
    monkeypatch.setattr(db_tool, "REDTEAM_PATH", path)
    with pytest.raises(ValueError):
        server.db_save_redteam_result(*args)
    assert not path.exists()
