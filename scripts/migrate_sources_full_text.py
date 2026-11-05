"""sources 增加 full_text 列（幂等迁移，默认预览）。

背景：判定链路要走"一次调用看整篇"（批次1-T2 路线 A），就必须有地方取整篇文本。
不重读原始文件：海报与扫描件重读要再跑一次 OCR（实测单张 4 秒起），
为了上下文而重跑识别等于用更慢换更准。

只加一列，不删除、不改任何既有列；重复执行输出"跳过"。
用法：
    python -m scripts.migrate_sources_full_text            # 预览 SQL
    python -m scripts.migrate_sources_full_text --apply    # 执行
    python -m scripts.migrate_sources_full_text --apply --show   # 附 SHOW CREATE TABLE 前后
"""

import argparse

from sqlalchemy import inspect, text

COLUMN = "ADD COLUMN `full_text` LONGTEXT NULL AFTER `item_count`"
STATEMENT = f"ALTER TABLE `sources` {COLUMN}"


def _columns(engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("sources")}


def _show_create(engine) -> str:
    with engine.connect() as connection:
        row = connection.execute(text("SHOW CREATE TABLE `sources`")).first()
    return row[1] if row and len(row) > 1 else "(表不存在)"


def migrate(engine, apply=False, show=False, emit=print) -> str:
    """检查列是否存在；预览不写入；执行失败原样抛出。"""
    has_column = "full_text" in _columns(engine)
    if has_column:
        emit("跳过：sources.full_text 已存在")
        return "skipped"
    emit(STATEMENT)
    if not apply:
        emit("仅预览；--apply 才执行")
        return "preview"
    before = _show_create(engine)
    with engine.begin() as connection:
        connection.execute(text(STATEMENT))
    emit("已执行：sources.full_text（LONGTEXT NULL）")
    if show:
        emit("\n=== 迁移前 sources ===\n" + before)
        emit("\n=== 迁移后 sources ===\n" + _show_create(engine))
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
