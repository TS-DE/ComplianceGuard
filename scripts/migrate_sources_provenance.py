"""新增 sources 表并为 scripts 补溯源列（幂等迁移，默认预览）。

背景：商家给的是整份素材（PDF/docx/Excel/PPT/海报图/录音），不是一条条话术。
解析层已经把"第几页、哪张表、第几句、OCR 置信度"都算出来了，但接口算完就丢——
`source = f"file:{filename}"` 甚至只在响应里出现，库里没有任何一列存它。
结果是：一条被判违规的话术，无法回答"这句是从哪来的"，也无法重跑或核对原文件。

本次改动（只加表、只加列，不删除也不改任何已有列）：
- 新表 `sources`：一份上传素材一行，存文件名/形态/引擎/内容指纹/落盘路径/结构化元信息/置信度/警告/耗时
- `scripts` 增加 4 列：source_id（指向素材）、source_pos、source_ref、parse_confidence

用法：
    python -m scripts.migrate_sources_provenance            # 预览将要执行的 SQL
    python -m scripts.migrate_sources_provenance --apply    # 执行
    python -m scripts.migrate_sources_provenance --apply --show   # 执行并打印前后 SHOW CREATE TABLE
"""

import argparse

from sqlalchemy import inspect, text

TABLE = "sources"
COLUMNS = {
    "source_id": "ADD COLUMN `source_id` BIGINT NULL AFTER `redteam_meta`",
    "source_pos": "ADD COLUMN `source_pos` INT NULL",
    "source_ref": "ADD COLUMN `source_ref` VARCHAR(40) NULL",
    "parse_confidence": "ADD COLUMN `parse_confidence` DECIMAL(5,4) NULL",
}
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS `sources` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `client_id` BIGINT NOT NULL,
  `filename` VARCHAR(255) NOT NULL,
  `kind` VARCHAR(20) NOT NULL,
  `engine` VARCHAR(40) NOT NULL,
  `sha256` VARCHAR(64) NOT NULL,
  `size_bytes` INT NOT NULL,
  `stored_path` VARCHAR(255) NULL,
  `meta` JSON NULL,
  `confidence` DECIMAL(5,4) NULL,
  `warnings` JSON NULL,
  `parse_ms` INT NULL,
  `item_count` INT NOT NULL DEFAULT 0,
  `created_by` BIGINT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_sources_client_id` (`client_id`),
  KEY `ix_sources_sha256` (`sha256`),
  CONSTRAINT `fk_sources_client` FOREIGN KEY (`client_id`)
    REFERENCES `clients` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_sources_user` FOREIGN KEY (`created_by`)
    REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _script_columns(inspector) -> set[str]:
    return {column["name"] for column in inspector.get_columns("scripts")}


def _show_create(engine, table: str) -> str:
    with engine.connect() as connection:
        row = connection.execute(text(f"SHOW CREATE TABLE `{table}`")).first()
    return row[1] if row and len(row) > 1 else "(表不存在)"


def migrate(engine, inspector=None, apply=False, show=False, emit=print) -> str:
    """检查结构差异；默认只预览。幂等：重复执行时已存在的表与列都会跳过。"""
    inspector = inspector or inspect(engine)
    has_table = TABLE in _table_names(inspector)
    columns = _script_columns(inspector)
    missing = [name for name in COLUMNS if name not in columns]

    if not has_table:
        emit(CREATE_TABLE.strip())
    if missing:
        # 一条 ALTER 加多列：分四次执行会把表锁四遍，中途失败还会留下半个状态
        emit("ALTER TABLE `scripts` " + ", ".join(COLUMNS[name] for name in missing))
        emit("ALTER TABLE `scripts` ADD CONSTRAINT `fk_scripts_source` "
             "FOREIGN KEY (`source_id`) REFERENCES `sources` (`id`) ON DELETE SET NULL")
        emit("ALTER TABLE `scripts` ADD INDEX `ix_scripts_source_id` (`source_id`)")
    if has_table and not missing:
        emit(f"跳过：{TABLE} 表已存在，scripts 溯源四列齐全")
        return "skipped"
    if not apply:
        emit("仅预览；--apply 才执行")
        return "preview"

    before = _show_create(engine, TABLE) if has_table else "(表不存在)"
    with engine.begin() as connection:
        if not has_table:
            connection.execute(text(CREATE_TABLE))
        if missing:
            connection.execute(text(
                "ALTER TABLE `scripts` " + ", ".join(COLUMNS[name] for name in missing)))
            connection.execute(text(
                "ALTER TABLE `scripts` ADD CONSTRAINT `fk_scripts_source` FOREIGN KEY "
                "(`source_id`) REFERENCES `sources` (`id`) ON DELETE SET NULL"))
            connection.execute(text(
                "ALTER TABLE `scripts` ADD INDEX `ix_scripts_source_id` (`source_id`)"))
    emit(f"已执行：{TABLE} 表 + scripts 溯源列（新增 {len(missing)} 列）")
    if show:
        emit("\n=== 迁移前 sources ===\n" + before)
        emit("\n=== 迁移后 sources ===\n" + _show_create(engine, TABLE))
        emit("\n=== 迁移后 scripts ===\n" + _show_create(engine, "scripts"))
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
