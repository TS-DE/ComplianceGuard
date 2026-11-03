"""资源生命周期业务编排：保留原函数签名与错误语义。"""
from sqlalchemy.orm import Session
from backend.core.config import DEFAULT_RULE_VERSION, RuleAxis
from backend.core.errors import BusinessValidationError, ConflictError
from backend.crud import special as repos
from backend.db.models import Client, Script, Audit, Rule
from backend.schemas.business import ClientCreate, ClientUpdate, ScriptCreate, ScriptUpdate, AuditCreate, AuditUpdate, RuleCreate, RuleUpdate
from backend.services.common import get_or_404, update_fields
VERSIONED_FIELDS = frozenset({"axis", "law_article", "pattern", "level", "example_bad"})
VALID_AXES = frozenset(a.value for a in RuleAxis)


def audit_operations(db, **kwargs):
    """服务层组合审查依赖，API 不绕过 service 直接操作持久化。"""
    from backend.tools.audit_tool import build_audit_tool
    return build_audit_tool(db, **kwargs)


class clients:
    """clients 生命周期编排。"""

    @staticmethod
    def get(db: Session, client_id: int) -> Client:
        """取机构，不存在 404。"""
        return get_or_404(repos.clients.get, db, 'client', client_id)

    @staticmethod
    def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Client], int]:
        """分页列表。"""
        return repos.clients.list_paged(db, page, page_size)

    @staticmethod
    def create(db: Session, payload: ClientCreate) -> Client:
        """新增机构。"""
        return repos.clients.create(db, payload.model_dump())

    @staticmethod
    def update(db: Session, client_id: int, payload: ClientUpdate) -> Client:
        """部分更新。"""
        return repos.clients.update(db, clients.get(db, client_id), update_fields(payload))

    @staticmethod
    def delete(db: Session, client_id: int) -> None:
        """删除机构；名下有话术 -> 409（与外键 RESTRICT 一致，提前给可读提示）。"""
        obj = clients.get(db, client_id)
        refs = repos.scripts.count_by_client(db, client_id)
        if refs:
            raise ConflictError(f"client {client_id} 名下仍有 {refs} 条话术，不能删除")
        repos.clients.delete(db, obj)

class scripts:
    """scripts 生命周期编排。"""

    @staticmethod
    def _ensure_client(db: Session, client_id: int) -> None:
        """body 里引用的机构不存在 -> 422（不是 404：路径资源存在，是入参不合法）。"""
        if repos.clients.get(db, client_id) is None:
            raise BusinessValidationError(f"client_id={client_id} 对应的机构不存在")

    @staticmethod
    def get(db: Session, script_id: int) -> Script:
        """取话术，不存在 404。"""
        return get_or_404(repos.scripts.get, db, 'script', script_id)

    @staticmethod
    def list_paged(
        db: Session, page: int, page_size: int, client_id: int | None
    ) -> tuple[list[Script], int]:
        """分页列表，可按机构过滤。"""
        return repos.scripts.list_paged(db, page, page_size, client_id)

    @staticmethod
    def create(db: Session, payload: ScriptCreate) -> Script:
        """新增话术。"""
        scripts._ensure_client(db, payload.client_id)
        return repos.scripts.create(db, payload.model_dump(mode="json"))

    @staticmethod
    def update(db: Session, script_id: int, payload: ScriptUpdate) -> Script:
        """部分更新；换归属时校验新机构存在。"""
        obj = scripts.get(db, script_id)
        data = update_fields(payload)
        if data.get("client_id") is not None:
            scripts._ensure_client(db, data["client_id"])
        if "status" in data and data["status"] is not None:
            data["status"] = data["status"].value
        return repos.scripts.update(db, obj, data)

    @staticmethod
    def delete(db: Session, script_id: int) -> None:
        """删除话术；已有审查记录 -> 409（审计留痕不能被连带删掉）。"""
        obj = scripts.get(db, script_id)
        refs = repos.audits.count_by_script(db, script_id)
        if refs:
            raise ConflictError(f"script {script_id} 已有 {refs} 条审查记录，不能删除")
        repos.scripts.delete(db, obj)

class audits:
    """audits 生命周期编排。"""

    @staticmethod
    def get(db: Session, audit_id: int) -> Audit:
        """取审查记录，不存在 404。"""
        return get_or_404(repos.audits.get, db, 'audit', audit_id)

    @staticmethod
    def list_paged(
        db: Session,
        page: int,
        page_size: int,
        client_id: int | None,
        script_id: int | None = None,
    ) -> tuple[list[Audit], int]:
        """分页列表，可按机构（经 scripts 关联）或单条话术过滤。

        script_id 用于「从话术库跳到它的审查记录」：一条话术可能被多次审查，
        因此这里返回该话术的全部审查历史，而不是最新一条。
        """
        return repos.audits.list_paged(db, page, page_size, client_id, script_id)

    @staticmethod
    def create(db: Session, payload: AuditCreate) -> Audit:
        """手工建审查记录（调试用）；话术必须存在。"""
        if repos.scripts.get(db, payload.script_id) is None:
            raise BusinessValidationError(f"script_id={payload.script_id} 对应的话术不存在")
        return repos.audits.create(db, payload.model_dump())

    @staticmethod
    def update(db: Session, audit_id: int, payload: AuditUpdate) -> Audit:
        """部分更新。"""
        return repos.audits.update(db, audits.get(db, audit_id), update_fields(payload))

    @staticmethod
    def delete(db: Session, audit_id: int) -> None:
        """删除审查记录。"""
        repos.audits.delete(db, audits.get(db, audit_id))

class rules:
    """rules 生命周期编排。"""

    @staticmethod
    def _ensure_axis(axis: str | None) -> None:
        """axis 不在 8 轴枚举内 -> 422（api_spec.md §3.1）。"""
        if axis is not None and axis not in VALID_AXES:
            raise BusinessValidationError(
                f"axis={axis} 不在规则轴枚举内，可选：{sorted(VALID_AXES)}"
            )

    @staticmethod
    def get(db: Session, rule_id: int) -> Rule:
        """取规则，不存在 404。"""
        return get_or_404(repos.rules.get, db, 'rule', rule_id)

    @staticmethod
    def list_paged(db: Session, page: int, page_size: int) -> tuple[list[Rule], int]:
        """分页列表。"""
        return repos.rules.list_paged(db, page, page_size)

    @staticmethod
    def create(db: Session, payload: RuleCreate) -> Rule:
        """新增规则，version 固定从 1 开始。"""
        rules._ensure_axis(payload.axis)
        data = payload.model_dump(mode="json")
        data["version"] = DEFAULT_RULE_VERSION
        return repos.rules.create(db, data)

    @staticmethod
    def update(db: Session, rule_id: int, payload: RuleUpdate) -> Rule:
        """部分更新；改内容则生成新版本行并停用旧行。"""
        old = rules.get(db, rule_id)
        data = update_fields(payload)
        rules._ensure_axis(data.get("axis"))
        if data.get("level") is not None:
            data["level"] = data["level"].value
        changed = {
            k for k in VERSIONED_FIELDS if k in data and data[k] != getattr(old, k)
        }
        if not changed:
            return repos.rules.update(db, old, data)

        snapshot = {k: getattr(old, k) for k in VERSIONED_FIELDS}
        snapshot.update({k: data[k] for k in VERSIONED_FIELDS if k in data})
        snapshot["enabled"] = data.get("enabled", old.enabled)
        snapshot["version"] = old.version + 1
        repos.rules.update(db, old, {"enabled": False})
        return repos.rules.create(db, snapshot)

    @staticmethod
    def delete(db: Session, rule_id: int) -> None:
        """删除规则（物理删）。"""
        repos.rules.delete(db, rules.get(db, rule_id))



def redteam_operations(db, model=None, auditor=None):
    """D4组合根；复用A1，不在API或Agent内执行SQL。"""
    from backend.agents.redteam import RedTeamAgent, JudgeAgent, AuditReportAgent
    from backend.tools.db_tool import RedteamRepository
    from backend.tools.audit_tool import UrllibChatModel
    return dict(repository=RedteamRepository(db),generator=RedTeamAgent(model or UrllibChatModel(purpose="redteam"),RedteamRepository(db).load_rules),
                judge=JudgeAgent(auditor or audit_operations(db)),report=AuditReportAgent(RedteamRepository(db),
                    (model or UrllibChatModel()) if __import__('os').environ.get('REPORT_USE_LLM','false').lower()=='true' else None))


def run_redteam(db, client_id, scenes, axes, model=None, auditor=None):
    """生成后顺序逐条审查，不重跑；连续四条未判定时停止并保留余项待判定。"""
    from uuid import uuid4
    from datetime import datetime
    ops=redteam_operations(db,model,auditor)
    run_id='rt_'+datetime.now().strftime('%Y%m%d_')+uuid4().hex[:8]
    batch=ops['generator'].generate(scenes,axes)
    ids=ops['repository'].save_samples(run_id,client_id,batch['samples'],batch['usage'])
    failed=0
    for row in ops['repository'].samples(run_id):
        result=ops['judge'].judge(row)
        ops['repository'].save_verdict(row['id'],result)
        failed=failed+1 if result['verdict']=='unjudged' else 0
        if failed>3: break
    return dict(run_id=run_id,generated=len(ids),script_ids=ids)
