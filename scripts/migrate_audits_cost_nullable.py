"""audits.cost 可空的最小幂等迁移，默认预览，不改任何既有金额。"""
import argparse
from sqlalchemy import inspect, text

DDL = 'ALTER TABLE `audits` MODIFY COLUMN `cost` DECIMAL(10,6) NULL DEFAULT NULL;'


def migrate(engine, inspector=None, apply=False, emit=print):
    """检查当前结构；预览无写入，执行失败原样抛出；返回执行状态。"""
    inspector = inspector or inspect(engine)
    column = next(c for c in inspector.get_columns('audits') if c['name'] == 'cost')
    if column['nullable']:
        emit('跳过：audits.cost 已可空')
        return 'skipped'
    emit(DDL)
    if not apply:
        emit('仅预览；--apply 才执行')
        return 'preview'
    with engine.begin() as connection:
        connection.execute(text(DDL))
    emit('已执行：audits.cost 可空')
    return 'applied'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    from backend.db.session import engine
    migrate(engine, apply=args.apply)


if __name__ == '__main__':
    main()
