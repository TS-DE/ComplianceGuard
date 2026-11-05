"""L3 人机回环：待复核队列 → 人工裁定 → 真值回流。

为什么必须有这一层：L1/L2 都是机器判定，`score=-1` 如果只在界面上挂个
「待人工复核」的标签而没有队列与裁定入口，就等于没有回环——机器拿不准的
记录永远没人处理，系统准确率也永远没有真值来源。

约定（用例即契约）：
- 入库即分类：未完成 / 疑似 / 含降级命中 → review_status='pending'；硬违规与合规 → NULL
- 裁定是终态：人工投入不能被后来的点击静默覆盖
- 越权按 404：不通过状态码泄漏"这条存在"
- 一致率分母只算已裁定记录，pending 不计入（否则会稀释真实一致率）
"""

from datetime import datetime

from fastapi.testclient import TestClient

API = "/api/v1"


def _merchant(client: TestClient, username: str) -> dict:
    """注册一个商家账号，返回 token/headers/client_id。"""
    created = client.post(f"{API}/auth/register", json={
        "username": username, "password": "Review12345",
        "role": "merchant", "client_name": f"{username}机构"})
    assert created.status_code == 200, created.text
    login = client.post(f"{API}/auth/login",
                        json={"username": username, "password": "Review12345"})
    data = login.json()["data"]
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"},
            "client_id": data["user"]["client_id"]}


def _make_audit(db, client_id: int, review_status: str | None = "pending", score: int = 0):
    """直接造一条审查记录，跳过真实模型调用。"""
    from backend.db.models import Audit, Client, Script

    account = db.get(Client, client_id)
    if account is None:
        account = Client(id=client_id, name=f"机构{client_id}",
                         industry="medical_beauty", contact=None, plan="free")
        db.add(account)
        db.commit()
    script = Script(client_id=client_id, content=f"待复核语料{client_id}", status="audited")
    db.add(script)
    db.commit()
    audit = Audit(script_id=script.id, score=score, hit_count=1, incomplete=False,
                  latency_ms=1, model="test", review_status=review_status,
                  hits_json=[{"axis": "efficacy_claim", "status": "active",
                              "quote": "待复核语料", "law_article": "广告法第16条"}])
    db.add(audit)
    db.commit()
    return audit


def test_enqueue_rule_covers_incomplete_suspect_and_downgraded() -> None:
    """入库即分类：三类必须进队列，硬违规与合规不进。"""
    from backend.crud.audit import AuditRepository

    needs = AuditRepository.needs_human_review
    assert needs({"incomplete": True}) is True
    assert needs({"score": 1}) is True
    assert needs({"score": 0, "hits": [{"downgraded": True}]}) is True
    assert needs({"score": 0, "hits": [{"severity": "hard"}]}) is False
    assert needs({"score": 2, "hits": []}) is False


def test_save_marks_pending_for_suspect_result(db) -> None:
    """落库时未完成的审查自动进队列，不依赖调用方记得设置。"""
    from backend.crud.audit import AuditRepository
    from backend.db.models import Audit, Client, Script

    account = Client(name="入库入队机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()
    script = Script(client_id=account.id, content="入库入队测试话术", status="pending")
    db.add(script)
    db.commit()

    repo = AuditRepository(db)
    audit_id = repo.save(script.id, {
        "hits": [], "raw_hits": [], "traces": [], "law_refs": [],
        "score": -1, "hit_count": 0, "model": "test",
        "prompt_tokens": 0, "completion_tokens": 0, "cost": None,
        "latency_ms": 0, "incomplete": True})
    assert db.get(Audit, audit_id).review_status == "pending"

    # 合规结果不进队列
    script2 = Script(client_id=account.id, content="入库入队测试话术二", status="pending")
    db.add(script2)
    db.commit()
    ok_id = repo.save(script2.id, {
        "hits": [], "raw_hits": [], "traces": [], "law_refs": [],
        "score": 2, "hit_count": 0, "model": "test",
        "prompt_tokens": 0, "completion_tokens": 0, "cost": None,
        "latency_ms": 0, "incomplete": False})
    assert db.get(Audit, ok_id).review_status is None


def test_queue_only_returns_own_pending(client: TestClient, db) -> None:
    """商家队列里不能出现别家机构的待复核记录。"""
    mine = _merchant(client, "review_mine")
    other = _merchant(client, "review_other")
    _make_audit(db, mine["client_id"], "pending")
    _make_audit(db, other["client_id"], "pending")

    resp = client.get(f"{API}/audit/review-queue", headers=mine["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["script_content"].startswith("待复核语料")


def test_review_confirmed_and_dismissed_persist(client: TestClient, db) -> None:
    """两种裁定都要落库，并带上裁定人。"""
    shop = _merchant(client, "review_action")
    first = _make_audit(db, shop["client_id"], "pending")
    second = _make_audit(db, shop["client_id"], "pending")

    ok = client.post(f"{API}/audit/{first.id}/review", headers=shop["headers"],
                     json={"verdict": "confirmed", "note": "确实是功效承诺"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["review_status"] == "confirmed"

    no = client.post(f"{API}/audit/{second.id}/review", headers=shop["headers"],
                     json={"verdict": "dismissed", "note": "属预后描述，误杀"})
    assert no.status_code == 200, no.text
    assert no.json()["data"]["review_status"] == "dismissed"

    from backend.db.models import Audit

    row = db.get(Audit, first.id)
    db.refresh(row)
    assert row.reviewed_by is not None and row.review_note == "确实是功效承诺"
    assert row.reviewed_at is not None


def test_review_is_not_silently_overwritten(client: TestClient, db) -> None:
    """人工裁定是终态：重复裁定必须报错，不能悄悄覆盖。"""
    shop = _merchant(client, "review_once")
    audit = _make_audit(db, shop["client_id"], "pending")
    first = client.post(f"{API}/audit/{audit.id}/review", headers=shop["headers"],
                        json={"verdict": "confirmed"})
    assert first.status_code == 200
    again = client.post(f"{API}/audit/{audit.id}/review", headers=shop["headers"],
                        json={"verdict": "dismissed"})
    # BusinessValidationError 经全局处理器映射为 422（与 /scripts/import 口径一致）
    assert again.status_code == 422
    assert "不可重复裁定" in again.json()["msg"]


def test_review_is_scope_guarded(client: TestClient, db) -> None:
    """越权裁定别家记录按 404 处理。"""
    mine = _merchant(client, "review_guard_a")
    other = _merchant(client, "review_guard_b")
    foreign = _make_audit(db, other["client_id"], "pending")

    resp = client.post(f"{API}/audit/{foreign.id}/review", headers=mine["headers"],
                       json={"verdict": "confirmed"})
    assert resp.status_code == 404


def test_review_stats_agree_rate_excludes_pending(client: TestClient, db) -> None:
    """一致率分母只算已裁定，pending 不能稀释。"""
    shop = _merchant(client, "review_stats")
    _make_audit(db, shop["client_id"], "pending")
    done_a = _make_audit(db, shop["client_id"], "pending")
    done_b = _make_audit(db, shop["client_id"], "pending")
    client.post(f"{API}/audit/{done_a.id}/review", headers=shop["headers"],
                json={"verdict": "confirmed"})
    client.post(f"{API}/audit/{done_b.id}/review", headers=shop["headers"],
                json={"verdict": "dismissed"})

    resp = client.get(f"{API}/audit/review-stats", headers=shop["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["pending"] == 1
    assert data["confirmed"] == 1 and data["dismissed"] == 1
    assert data["judged"] == 2
    assert data["agree_rate"] == 0.5
