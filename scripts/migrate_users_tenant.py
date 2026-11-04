"""users 增加商家归属与 merchant 角色（幂等迁移，默认预览）。

背景：此前所有登录用户权限完全相同，`users` 也没有任何"属于哪个机构"的字段，
因此系统只能做成一个平台后台，无法提供商家自助端——
商家要把文案交给管理员逐条录入，效率不可接受。

本次补上多租户地基：
- `users.client_id`：商家账号绑定到具体机构；平台管理员为 NULL
- `role` 枚举增加 `merchant`

迁移只做加列与改枚举，不删除、不改动已有数据；已有账号保持原角色。
"""

import argparse

from sqlalchemy import inspect, text

ADD_COLUMN = (
    "ALTER TABLE `users` "
    "ADD COLUMN `client_id` BIGINT NULL AFTER `role`, "
    "ADD CONSTRAINT `fk_users_client` FOREIGN KEY (`client_id`) "
    "REFERENCES `clients` (`id`) ON DELETE SET NULL"
)
WIDEN_ROLE = (
    "ALTER TABLE `users` MODIFY COLUMN `role` "
    "ENUM('admin','operator','merchant') NOT NULL DEFAULT 'operator'"
)


def _role_column_type(connection) -> str:
    """直接查 information_schema 拿 COLUMN_TYPE。

    不用 inspector.get_columns 的 type 表示：它返回的是 SQLAlchemy 的 ENUM 对象，
    字符串化后不含枚举值，导致"是否已含 merchant"判断永远为真、迁移不幂等。
    """
    row = connection.execute(text(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'role'"
    )).first()
    return (row[0] if row else "").lower()


def migrate(engine, inspector=None, apply=False, emit=print):
    """检查当前结构；预览不写入，执行失败原样抛出；返回执行状态。"""
    inspector = inspector or inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.connect() as connection:
        role_type = _role_column_type(connection)
    needs_enum = "merchant" not in role_type
    needs_column = "client_id" not in columns

    if not needs_column and not needs_enum:
        emit("跳过：users 已有 client_id 与 merchant 角色")
        return "skipped"

    if needs_column:
        emit(ADD_COLUMN)
    if needs_enum:
        emit(WIDEN_ROLE)
    if not apply:
        emit("仅预览；--apply 才执行")
        return "preview"

    with engine.begin() as connection:
        if needs_column:
            connection.execute(text(ADD_COLUMN))
        if needs_enum:
            connection.execute(text(WIDEN_ROLE))
    emit("已执行：users 增加 client_id 与 merchant 角色")
    return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from backend.db.session import engine

    migrate(engine, apply=args.apply)


if __name__ == "__main__":
    main()
