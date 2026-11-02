"""Preview authorized rules-only additions; use --apply to execute DDL.

MySQL DDL auto-commits. Any error stops immediately; reruns inspect missing
columns so a partially completed migration can be safely resumed.
"""
import argparse
from sqlalchemy import create_engine, inspect, text
from backend.core.config import settings


COLUMN_DDL = {
    "detector": "ALTER TABLE `rules` ADD COLUMN `detector` ENUM('keyword','regex','semantic','llm_judge') NOT NULL DEFAULT 'llm_judge' AFTER `level`",
    "exemptions": "ALTER TABLE `rules` ADD COLUMN `exemptions` JSON NULL AFTER `detector`",
}


def plan_migration(connection):
    """Reflect actual columns, including partially migrated databases."""
    existing = {column["name"] for column in inspect(connection).get_columns("rules")}
    return [ddl for name, ddl in COLUMN_DDL.items() if name not in existing]


def main(argv=None):
    """Print exact planned DDL by default; never suppress DDL failures."""
    parser = argparse.ArgumentParser(description="rules 两列授权迁移")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    engine = create_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            statements = plan_migration(connection)
            if not statements:
                print("两列已存在，跳过")
                return 0
            print("DDL 执行" if args.apply else "DDL 预览（未执行；--apply 才写库）")
            for statement in statements:
                print(statement + ";")
                if args.apply:
                    connection.execute(text(statement))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
