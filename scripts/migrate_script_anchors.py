"""scripts 增加 source_start / source_end 绝对偏移列（幂等迁移，默认预览）。

背景：分段锚点此前只有 source_pos，粒度是"块"（第 3 页 / 表格第 12 行）。
同一块里出现两句完全相同的话术时，靠 pos 分不开，界面只能退回模糊定位，
于是出现"1 处命中在原文里定位失败"。锚点必须落成整篇文本里的字符区间。

只加两列，不删除、不改任何既有列；两列各自幂等，重复执行输出"跳过"。
用法：
    python -m scripts.migrate_script_anchors                   # 预览 SQL
    python -m scripts.migrate_script_anchors --apply           # 执行
    python -m scripts.migrate_script_anchors --apply --show    # 附 SHOW CREATE TABLE 前后
"""

import argparse

from sqlalchemy import inspect, text

COLUMNS = (
    ("source_start", "ADD COLUMN `source_start` INT NULL AFTER `source_pos`"),
    ("source_end", "ADD COLUMN `source_end` INT NULL AFTER `source_start`"),
)


def _columns(engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("scripts")}


def _show_create(engine) -> str:
    with engine.connect() as connection:
        row = connection.execute(text("SHOW CREATE TABLE `scripts`")).first()
    return row[1] if row and len(row) > 1 else "(表不存在)"


def migrate(engine, apply=False, show=False, emit=print) -> str:
    """逐列检查存在性；预览不写入；执行失败原样抛出（不静默跳过半截）。"""
    present, statements = _columns(engine), []
    for name, definition in COLUMNS:
        if name in present:
            emit(f"跳过：scripts.{name} 已存在")
            continue
        statements.append(f"ALTER TABLE `scripts` {definition}")
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
    emit(f"已执行：scripts 增加 {len(statements)} 列（INT NULL）")
    if show:
        emit("\n=== 迁移前 scripts ===\n" + before)
        emit("\n=== 迁移后 scripts ===\n" + _show_create(engine))
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
