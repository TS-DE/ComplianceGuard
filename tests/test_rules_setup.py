"""Rules setup safety tests; isolated from business DB and shared cleanup."""
import importlib
import importlib.util
import json
from pathlib import Path
from sqlalchemy import create_engine, text

import pytest


@pytest.fixture(autouse=True)
def clean_tables():
    """These tests use their own connections, never the production DB."""
    yield


def load_module(name):
    assert importlib.util.find_spec(name) is not None, f"Missing setup module: {name}"
    return importlib.import_module(name)


def test_migration_previews_only_authorized_columns(monkeypatch):
    migration = load_module("scripts.migrate_rules_columns")
    class Inspector:
        def get_columns(self, table):
            assert table == "rules"
            return [{"name": "level"}]
    monkeypatch.setattr(migration, "inspect", lambda connection: Inspector())
    assert migration.plan_migration(object()) == [
        "ALTER TABLE `rules` ADD COLUMN `detector` ENUM('keyword','regex','semantic','llm_judge') NOT NULL DEFAULT 'llm_judge' AFTER `level`",
        "ALTER TABLE `rules` ADD COLUMN `exemptions` JSON NULL AFTER `detector`",
    ]


@pytest.mark.parametrize("existing,expected", [({"detector"}, 1), ({"exemptions"}, 1), ({"detector", "exemptions"}, 0)])
def test_partial_migration_and_rerun(monkeypatch, existing, expected):
    migration = load_module("scripts.migrate_rules_columns")
    class Inspector:
        def get_columns(self, table):
            return [{"name": name} for name in existing]
    monkeypatch.setattr(migration, "inspect", lambda connection: Inspector())
    assert len(migration.plan_migration(object())) == expected


def test_migration_default_preview_and_ddl_error_stop(monkeypatch, capsys):
    migration = load_module("scripts.migrate_rules_columns")
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, statement):
            raise RuntimeError("DDL failure")
    class Engine:
        def begin(self): return Connection()
        def dispose(self): pass
    monkeypatch.setattr(migration, "create_engine", lambda dsn: Engine())
    monkeypatch.setattr(migration, "plan_migration", lambda conn: list(migration.COLUMN_DDL.values()))
    assert migration.main([]) == 0
    assert "预览" in capsys.readouterr().out
    with pytest.raises(RuntimeError, match="DDL failure"):
        migration.main(["--apply"])


def test_seed_preview_apply_sql_null_and_idempotence():
    seed = load_module("scripts.seed_rules")
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE rules (id INTEGER PRIMARY KEY, axis VARCHAR(40), law_article VARCHAR(80), pattern VARCHAR(200), level VARCHAR(10), detector VARCHAR(20), exemptions JSON, example_bad TEXT, version INTEGER, enabled BOOLEAN)"))
        preview = seed.seed_rules(conn)
        assert preview["inserted"] == 0
        assert conn.execute(text("SELECT COUNT(*) FROM rules")).scalar_one() == 0
        first = seed.seed_rules(conn, apply=True)
        assert first["inserted"] == 11
        assert first["total"] == 11
        assert first["detectors"] == {"regex": 3, "llm_judge": 8}
        assert conn.execute(text("SELECT COUNT(*) FROM rules WHERE exemptions IS NOT NULL")).scalar_one() == 1
        assert conn.execute(text("SELECT json_array_length(exemptions) FROM rules WHERE axis='absolute_terms'")).scalar_one() == 9
        second = seed.seed_rules(conn, apply=True)
        assert second["inserted"] == 0
        assert second["skipped"] == 11
        assert second["total"] == 11
    engine.dispose()


def test_seed_cli_previews_by_default_and_rejects_wrong_count(monkeypatch):
    seed = load_module("scripts.seed_rules")
    calls = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Engine:
        def begin(self): return Connection()
        def dispose(self): pass
    monkeypatch.setattr(seed, "create_engine", lambda dsn: Engine())
    def run(conn, apply=False):
        calls.append(apply)
        return {"total": 0, "inserted": 0, "pending": 11, "skipped": 0, "detectors": {}}
    monkeypatch.setattr(seed, "seed_rules", run)
    assert seed.main([]) == 0
    assert calls == [False]
    with pytest.raises(RuntimeError, match="11"):
        seed.main(["--apply"])


def test_scope_exemptions_preserve_original_source_records():
    constants = load_module("backend.core.constants")
    records = json.loads((Path(__file__).resolve().parents[1] / "data/seeds/rules.json").read_text(encoding="utf-8"))
    assert constants.SCOPE_EXEMPTIONS == records["scope_exemptions"]
    assert len(constants.SCOPE_EXEMPTIONS) == 4
