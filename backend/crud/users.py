"""users 表读写：纯数据库操作。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.users import User


def get_by_id(db: Session, user_id: int) -> User | None:
    """按主键取用户，不存在返回 None。"""
    return db.get(User, user_id)


def get_by_username(db: Session, username: str) -> User | None:
    """按登录名取用户；username 上有唯一索引。"""
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def create(db: Session, username: str, password_hash: str, role: str) -> User:
    """插入用户并提交，返回带自增 id 的实例。"""
    user = User(username=username, password_hash=password_hash, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
