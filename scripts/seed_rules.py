"""Preview the 11 seed rules; --apply inserts missing (axis, version) only.

Reflection intentionally avoids ORM schema dependencies. No tables are created
or altered; absent exemptions bind SQL NULL, not the JSON literal null.
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, func, null, select
from backend.core.config import settings

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seeds" / "rules.json"


def seed_rules(connection, apply=False, seed_path=SEED_PATH):
    """Insert only missing axis/version pairs; leave existing rules unchanged."""
    records = json.loads(Path(seed_path).read_text(encoding="utf-8"))["rules"]
    table = Table("rules", MetaData(), autoload_with=connection)
    existing = set(connection.execute(select(table.c.axis, table.c.version)).tuples())
    pending = [record for record in records if (record["axis"], record.get("version", 1)) not in existing]
    if apply:
        for record in pending:
            values = dict(record, version=record.get("version", 1), enabled=True)
            if values.get("exemptions") is None:
                values["exemptions"] = null()
            connection.execute(table.insert().values(**values))
    total = connection.execute(select(func.count()).select_from(table)).scalar_one()
    distribution = {detector: count for detector, count in connection.execute(select(table.c.detector, func.count()).group_by(table.c.detector))}
    return {"inserted": len(pending) if apply else 0, "pending": len(pending),
            "skipped": len(records) - len(pending), "total": total, "detectors": distribution}


def main(argv=None):
    """Default preview; count mismatch rolls back seed DML and stops."""
    parser = argparse.ArgumentParser(description="rules 种子数据")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    engine = create_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            report = seed_rules(connection, apply=args.apply)
            print("种子执行" if args.apply else "种子预览（未执行；--apply 才写库）")
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            if args.apply and report["total"] != 11:
                raise RuntimeError(f"rules count={report['total']} != 11; 已停止并回滚")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
