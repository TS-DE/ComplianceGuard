"""契约回归：`audits.cost` 可空化后，响应模型与列表接口必须同步。

背景（2026-11-03 实测）：D3 把 `audits.cost` 迁移为可空（NULL=未配置单价未计价），
但 `AuditOut.cost` 仍是必填 `Decimal`。只要表里存在一行 `cost IS NULL`，
`GET /api/v1/audits` 就会在序列化时抛 ValidationError，整个列表 500；
而 `GET /api/v1/audits/{id}` 若恰好取到有值的行则正常——这种"列表挂了、详情正常"
的不对称故障极易被漏掉。本用例锁死该契约。
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_audit_out_accepts_null_cost() -> None:
    """模型层：cost 为 None 必须能通过校验，且序列化后仍是 None（不是 0）。"""
    from decimal import Decimal

    from backend.schemas.business import AuditOut

    payload = dict(
        id=1, script_id=1, score=0, hit_count=0, hits_json=None, law_refs_json=None,
        rewritten_text=None, rewrite_passed=None, model="qwen3.8-flash",
        prompt_tokens=10, completion_tokens=5, cost=None, latency_ms=1,
        incomplete=False, created_at="2026-11-03T10:00:00",
    )
    out = AuditOut.model_validate(payload)
    dumped = out.model_dump(mode="json")
    assert dumped["cost"] is None, "未计价必须保持 NULL 语义，不许被填成 0"

    out2 = AuditOut.model_validate({**payload, "cost": Decimal("0.013745")})
    assert out2.model_dump(mode="json")["cost"] == "0.013745"


def test_audits_list_survives_null_cost_row(client: TestClient, auth_headers: dict, db: Session) -> None:
    """接口层：库里存在 cost=NULL 的行时，列表接口必须 200 且该行 cost 为 null。"""
    from backend.db.models import Audit, Client, Script

    account = Client(name="契约测试机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.flush()
    script = Script(client_id=account.id, scene="双眼皮", content="保证白一个色度")
    db.add(script)
    db.flush()
    db.add(Audit(
        script_id=script.id, score=0, hit_count=0, hits_json=None, law_refs_json=None,
        rewritten_text=None, rewrite_passed=None, model="qwen3.8-flash",
        prompt_tokens=10, completion_tokens=5, cost=None, latency_ms=1, incomplete=False,
    ))
    db.commit()

    resp = client.get("/api/v1/audits", headers=auth_headers)
    assert resp.status_code == 200, f"列表不应因 NULL 成本行整体 500：{resp.text[:200]}"
    body = resp.json()
    assert body["code"] == 200
    assert body["total"] == 1
    assert body["data"][0]["cost"] is None

    detail = client.get(f"/api/v1/audits/{body['data'][0]['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["cost"] is None
