"""audits 增加人工复核字段（幂等迁移，默认预览）。

背景：L1（规则/词库）与 L2（上下文判定 + 分级闸）都有了，但 L3 缺失——
`score=-1` 只在界面上打了「待人工复核」的标签，没有队列、没有裁定入口、没有回流，
等于标签挂着没人能处理。

补上之后形成闭环：
    机器分级 → 待复核队列 → 人工裁定（确认/推翻）→ 真值落库 → 一致率与规则候选

字段语义：
- review_status = NULL       无需复核（结论明确且非疑似）
- review_status = 'pending'  在待复核队列里
- review_status = 'confirmed' 人工确认系统判定正确
- review_status = 'dismissed' 人工推翻系统判定（误杀或漏判被修正）
"""

import argparse

from sqlalchemy import inspect, text

COLUMNS = {
    "review_status": (
        "ALTER TABLE `audits` ADD COLUMN `review_status` "
        "ENUM('pending','confirmed','dismissed') NULL DEFAULT NULL"
    ),
    "reviewed_by": (
        "ALTER TABLE `audits` ADD COLUMN `reviewed_by` BIGINT NULL"
    ),
    "review_note": (
        "ALTER TABLE `audits` ADD COLUMN `review_note` VARCHAR(500) NULL"
    ),
    "reviewed_at": (
        "ALTER TABLE `audits` ADD COLUMN `reviewed_at` DATETIME NULL"
    ),
}


def migrate(engine, inspector=None, apply=False, emit=print):
    """检查当前结构；预览不写入，执行失败原样抛出；返回执行状态。"""
    inspector = inspector or inspect(engine)
    existing = {column["name"] for column in inspector.get_columns("audits")}
    missing = [name for name in COLUMNS if name not in existing]
    if not missing:
        emit("跳过：audits 已有全部复核字段")
        return "skipped"

    for name in missing:
        emit(COLUMNS[name])
    if not apply:
        emit("仅预览；--apply 才执行")
        return "preview"

    with engine.begin() as connection:
        for name in missing:
            connection.execute(text(COLUMNS[name]))
    emit(f"已执行：audits 增加 {', '.join(missing)}")
    return "applied"


def backfill(engine, apply=False, emit=print):
    """把历史记录按同一口径回填进复核队列。

    迁移只加列，历史记录全是 NULL；若不回填，待复核队列在演示时是空的，
    看起来像"系统从没拿不准过"。口径与入库时一致：
    未完成、分数为 1、或命中里含降级标记 -> pending。
    只写入 pending，不覆盖已有裁定。
    """
    from sqlalchemy import text

    suspect = (
        "UPDATE `audits` SET `review_status` = 'pending' "
        "WHERE `review_status` IS NULL AND ("
        "  `incomplete` = 1 OR `score` = 1 "
        "  OR JSON_SEARCH(`hits_json`, 'one', 'true', NULL, '$[*].downgraded') IS NOT NULL)"
    )
    with engine.connect() as connection:
        will_change = connection.execute(text(
            "SELECT COUNT(*) FROM `audits` WHERE `review_status` IS NULL AND ("
            "`incomplete` = 1 OR `score` = 1)")).scalar()
    emit(f"将回填 {will_change} 条为 pending（未完成 + 疑似）")
    if not apply:
        emit("仅预览；--apply --backfill 才执行")
        return "preview"
    with engine.begin() as connection:
        result = connection.execute(text(suspect))
    emit(f"已回填 {result.rowcount} 条")
    return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backfill", action="store_true",
                        help="把历史记录按同一口径回填进复核队列")
    args = parser.parse_args()
    from backend.db.session import engine

    migrate(engine, apply=args.apply)
    if args.backfill or not args.apply:
        backfill(engine, apply=args.apply and args.backfill)


if __name__ == "__main__":
    main()
