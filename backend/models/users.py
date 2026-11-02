"""users：账号表（db_schema.md §1.1）。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.config import UserRole
from backend.db.base import Base, MYSQL_TABLE_ARGS


class User(Base):
    """登录账号；密码只存 bcrypt 哈希，禁止明文。"""

    __tablename__ = "users"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # ENUM 用 native_enum 默认行为即可，MySQL 侧生成 ENUM('admin','operator')
    role: Mapped[str] = mapped_column(
        Enum(UserRole, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'operator'"),
    )
    # TINYINT(1)：MySQL 里 Boolean 会生成为 TINYINT(1)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"
