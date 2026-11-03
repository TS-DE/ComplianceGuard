"""scripts红队来源列幂等迁移，默认预览，仅--apply执行。"""
import argparse
from sqlalchemy import inspect, text

DDL = {
    'source': "ALTER TABLE `scripts` ADD COLUMN `source` ENUM('manual','redteam') NOT NULL DEFAULT 'manual' AFTER `scene`",
    'redteam_meta': 'ALTER TABLE `scripts` ADD COLUMN `redteam_meta` JSON NULL AFTER `source`',
}


def plan(inspector):
    """按已存在列生成最小补列计划，不写数据库。"""
    existing = {c['name'] for c in inspector.get_columns('scripts')}
    return [sql for name, sql in DDL.items() if name not in existing]


def migrate(engine, apply=False):
    """预览或执行；已有列跳过，DDL错误直接上抛。"""
    statements = plan(inspect(engine))
    if not statements:
        print('跳过：scripts红队列已存在')
    for sql in statements:
        print(sql + ';')
        if apply:
            with engine.begin() as conn:
                conn.execute(text(sql))
    return statements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    from backend.db.session import engine
    migrate(engine, parser.parse_args().apply)


if __name__ == '__main__':
    main()
