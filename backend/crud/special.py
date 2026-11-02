"""资源查询特例与兼容的 CRUD 函数命名空间。"""
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend.crud.base import Repository, paginate
from backend.db.models import Client, Script, Audit, Rule, User


class clients:
    """Client 资源持久化入口。"""

    @staticmethod
    def get(db: Session, client_id: int) -> Client | None:
        """按主键取机构，不存在返回 None。"""
        return db.get(Client, client_id)

    @staticmethod
    def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Client], int]:
        """按 id 倒序分页。"""
        stmt = select(Client).order_by(Client.id.desc())
        return paginate(db, stmt, page, page_size)

    @staticmethod
    def create(db: Session, data: dict[str, Any]) -> Client:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Client).create(db, data)

    @staticmethod
    def update(db: Session, obj: Client, data: dict[str, Any]) -> Client:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Client).update(db, obj, data)

    @staticmethod
    def delete(db: Session, obj: Client) -> None:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Client).delete(db, obj)

class scripts:
    """Script 资源持久化入口。"""

    @staticmethod
    def get(db: Session, script_id: int) -> Script | None:
        """按主键取话术。"""
        return db.get(Script, script_id)

    @staticmethod
    def list_paged(
        db: Session, page: int, page_size: int, client_id: int | None = None
    ) -> tuple[list[Script], int]:
        """分页查询，可选按 client_id 过滤。"""
        stmt = select(Script).order_by(Script.id.desc())
        if client_id is not None:
            stmt = stmt.where(Script.client_id == client_id)
        return paginate(db, stmt, page, page_size)

    @staticmethod
    def create(db: Session, data: dict[str, Any]) -> Script:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Script).create(db, data)

    @staticmethod
    def update(db: Session, obj: Script, data: dict[str, Any]) -> Script:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Script).update(db, obj, data)

    @staticmethod
    def delete(db: Session, obj: Script) -> None:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Script).delete(db, obj)

    @staticmethod
    def count_by_client(db: Session, client_id: int) -> int:
        """统计某机构名下话术数（删除机构前的引用检查）。"""
        stmt = select(func.count()).select_from(Script).where(Script.client_id == client_id)
        return int(db.execute(stmt).scalar_one())

class audits:
    """Audit 资源持久化入口。"""

    @staticmethod
    def get(db: Session, audit_id: int) -> Audit | None:
        """按主键取审查记录。"""
        return db.get(Audit, audit_id)

    @staticmethod
    def list_paged(
        db: Session,
        page: int,
        page_size: int,
        client_id: int | None = None,
    ) -> tuple[list[Audit], int]:
        """分页查询；client_id 过滤需 join scripts（audits 本身没有该列）。"""
        stmt = select(Audit).order_by(Audit.id.desc())
        if client_id is not None:
            stmt = stmt.join(Script, Audit.script_id == Script.id).where(
                Script.client_id == client_id
            )
        return paginate(db, stmt, page, page_size)

    @staticmethod
    def create(db: Session, data: dict[str, Any]) -> Audit:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Audit).create(db, data)

    @staticmethod
    def update(db: Session, obj: Audit, data: dict[str, Any]) -> Audit:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Audit).update(db, obj, data)

    @staticmethod
    def delete(db: Session, obj: Audit) -> None:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Audit).delete(db, obj)

    @staticmethod
    def count_by_script(db: Session, script_id: int) -> int:
        """统计某话术的审查记录数（删除话术前的引用检查）。"""
        stmt = select(func.count()).select_from(Audit).where(Audit.script_id == script_id)
        return int(db.execute(stmt).scalar_one())

class rules:
    """Rule 资源持久化入口。"""

    @staticmethod
    def get(db: Session, rule_id: int) -> Rule | None:
        """按主键取规则。"""
        return db.get(Rule, rule_id)

    @staticmethod
    def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Rule], int]:
        """按 id 倒序分页。"""
        stmt = select(Rule).order_by(Rule.id.desc())
        return paginate(db, stmt, page, page_size)

    @staticmethod
    def create(db: Session, data: dict[str, Any]) -> Rule:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Rule).create(db, data)

    @staticmethod
    def update(db: Session, obj: Rule, data: dict[str, Any]) -> Rule:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Rule).update(db, obj, data)

    @staticmethod
    def delete(db: Session, obj: Rule) -> None:
        """委托通用仓储，保留原调用签名与提交语义。"""
        return Repository(Rule).delete(db, obj)

class users:
    """User 资源持久化入口。"""

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> User | None:
        """按主键取用户，不存在返回 None。"""
        return db.get(User, user_id)

    @staticmethod
    def get_by_username(db: Session, username: str) -> User | None:
        """按登录名取用户；username 上有唯一索引。"""
        stmt = select(User).where(User.username == username)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def create(db: Session, username: str, password_hash: str, role: str) -> User:
        """插入用户并提交，返回带自增 id 的实例。"""
        user = User(username=username, password_hash=password_hash, role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
