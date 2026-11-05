"""Versioned seed rules; insert changed snapshots and disable old versions.

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
    """Insert immutable changed snapshots; only disable old enabled flags."""
    records = json.loads(Path(seed_path).read_text(encoding="utf-8"))["rules"]
    table = Table("rules", MetaData(), autoload_with=connection)
    pending = []
    for record in records:
        history = connection.execute(select(table).where(table.c.axis == record['axis'])
                                     .order_by(table.c.version.desc()).with_for_update()).mappings().all()
        latest = history[0] if history else None
        content_keys = [key for key in record if key not in ('version', 'enabled')]
        if latest and all(latest[key] == record[key] for key in content_keys):
            continue
        version = (latest['version'] + 1) if latest else record.get('version', 1)
        if latest and record.get('version', version) != version:
            raise ValueError('seed version must equal latest version + 1')
        pending.append((record, version))
        if apply:
            # 唯一允许修改旧行的字段为停用标记；内容和版本从不覆盖。
            connection.execute(table.update().where(table.c.axis == record['axis'],
                               table.c.enabled.is_(True)).values(enabled=False))
            values = dict(record, version=version, enabled=True)
            if values.get('exemptions') is None:
                values['exemptions'] = null()
            connection.execute(table.insert().values(**values))
    total = connection.execute(select(func.count()).select_from(table)).scalar_one()
    # 历史版本行必须保留（铁律 7），所以总行数会随每次改动增长，不能拿它当不变量；
    # 真正的不变量是「每个轴恰好一条 enabled」，多一条即同轴重复计分。
    enabled = connection.execute(select(func.count()).select_from(table)
                                 .where(table.c.enabled.is_(True))).scalar_one()
    axis_counts = dict(connection.execute(select(table.c.axis, func.count())
                       .where(table.c.enabled.is_(True)).group_by(table.c.axis)).all())
    distribution = {detector: count for detector, count in connection.execute(select(table.c.detector, func.count()).group_by(table.c.detector))}
    return {"inserted": len(pending) if apply else 0, "pending": len(pending),
            "skipped": len(records) - len(pending), "total": total,
            "enabled": enabled, "axes": len(axis_counts),
            "duplicates": sorted(a for a, n in axis_counts.items() if n != 1),
            "detectors": distribution}


def main(argv=None):
    """Default preview; invariant breach rolls back seed DML and stops."""
    parser = argparse.ArgumentParser(description="rules 种子数据")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    engine = create_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            report = seed_rules(connection, apply=args.apply)
            print("种子执行" if args.apply else "种子预览（未执行；--apply 才写库）")
            print(json.dumps({k: v for k, v in report.items() if k != "detectors"},
                             ensure_ascii=False, sort_keys=True))
            if args.apply and (report["duplicates"] or report["enabled"] != report["axes"]):
                raise RuntimeError(
                    f"enabled 规则数 {report['enabled']} / 轴数 {report['axes']}，"
                    f"重复轴 {report['duplicates']}；已停止并回滚")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
