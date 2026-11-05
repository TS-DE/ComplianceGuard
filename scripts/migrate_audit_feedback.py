"""audits 增加商家反馈两列（幂等迁移，默认预览）。

背景：商家端要能对本次判定说一句"有用 / 没用"。这两个字段**不参与判定**，
也刻意不与 `review_*` 复用：`review_*` 是运营的人工改判（有处置权、进审计轨迹），
feedback_* 只是主观反馈。混用的后果是商家点一下"没用"，
报表里就成了"人工推翻系统判定"，把两个完全不同的动作记成同一件事。

只加列，不删除、不改任何既有列；两列各自幂等，重复执行输出"跳过"。
用法：
    python -m scripts.migrate_audit_feedback             # 预览 SQL
    python -m scripts.migrate_audit_feedback --apply     # 执行
    python -m scripts.migrate_audit_feedback --apply --show   # 附 SHOW CREATE TABLE 前后
"""

import argparse

from sqlalchemy import inspect, text

COLUMNS = (
    ("feedback",
     "ADD COLUMN `feedback` ENUM('useful','not_useful') NULL COMMENT '商家反馈：不参与判定'"),
    ("feedback_note",
     "ADD COLUMN `feedback_note` VARCHAR(500) NULL COMMENT '反馈补充说明，可为空'"),
)


def _columns(engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("audits")}


def _show_create(engine) -> str:
    with engine.connect() as connection:
        row = connection.execute(text("SHOW CREATE TABLE `audits`")).first()
    return row[1] if row and len(row) > 1 else "(表不存在)"


def migrate(engine, apply=False, show=False, emit=print) -> str:
    """逐列检查存在性；预览不写入；执行失败原样抛出。"""
    present, statements = _columns(engine), []
    for name, definition in COLUMNS:
        if name in present:
            emit(f"跳过：audits.{name} 已存在")
            continue
        statements.append(f"ALTER TABLE `audits` {definition}")
    if not statements:
        return "skipped"
    for statement in statements:
        emit(statement)
    if not apply:
        emit("仅预览；--apply 才执行")
        return "preview"
    before = _show_create(engine)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    emit(f"已执行：audits 增加 {len(statements)} 列（均 NULL 允许，不回填历史数据）")
    if show:
        emit("\n=== 迁移前 audits ===\n" + before)
        emit("\n=== 迁移后 audits ===\n" + _show_create(engine))
    return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="真正执行 SQL")
    parser.add_argument("--show", action="store_true", help="打印迁移前后 SHOW CREATE TABLE")
    args = parser.parse_args()
    from backend.db.session import engine

    migrate(engine, apply=args.apply, show=args.show)


if __name__ == "__main__":
    main()
