"""多租户隔离与批量审查。

这两块是「商家端」能不能对外提供的地基：
- 商家必须**只能**看到自己机构的数据，否则一个商家能看到同行的话术与违规记录；
- 平台级功能（规则库）必须挡住商家，否则等于让被审查方修改审查标准；
- 越权访问单条资源要按 404 处理，不能通过状态码泄漏"这条存在"。

测试用真实 HTTP（TestClient），不直接调 service，避免绕过路由层的作用域逻辑。
"""

from fastapi.testclient import TestClient

API = "/api/v1"


def _register(client: TestClient, username: str, role: str, client_name: str | None = None) -> dict:
    """注册并登录，返回 {token, user}。"""
    payload = {"username": username, "password": "Tenant12345", "role": role}
    if client_name is not None:
        payload["client_name"] = client_name
    created = client.post(f"{API}/auth/register", json=payload)
    assert created.status_code == 200, created.text
    login = client.post(f"{API}/auth/login",
                        json={"username": username, "password": "Tenant12345"})
    assert login.status_code == 200, login.text
    data = login.json()["data"]
    return {"token": data["access_token"], "user": data["user"],
            "headers": {"Authorization": f"Bearer {data['access_token']}"}}


def test_merchant_registration_creates_and_binds_client(client: TestClient) -> None:
    """商家注册必须同时建机构并绑定，否则自助端第一步就断。"""
    shop = _register(client, "shop_alpha", "merchant", "阿尔法医美")
    assert shop["user"]["role"] == "merchant"
    assert shop["user"]["client_id"] is not None

    mine = client.get(f"{API}/clients", headers=shop["headers"])
    assert mine.status_code == 200
    body = mine.json()
    assert body["total"] == 1
    assert body["data"][0]["id"] == shop["user"]["client_id"]


def test_admin_registration_has_no_client(client: TestClient) -> None:
    """平台管理员不绑定机构，因此可看全部。"""
    boss = _register(client, "boss_admin", "admin")
    assert boss["user"]["client_id"] is None


def test_merchant_cannot_read_platform_rules(client: TestClient) -> None:
    """商家不能读规则库：被审查方不该能查看或修改审查标准。"""
    shop = _register(client, "shop_rule", "merchant", "规则测试机构")
    resp = client.get(f"{API}/rules", headers=shop["headers"])
    assert resp.status_code == 403
    assert "管理员" in resp.json()["msg"]


def test_merchant_only_sees_own_scripts(client: TestClient, auth_headers: dict, db) -> None:
    """商家列表里不能出现别家机构的话术。"""
    from backend.db.models import Client, Script

    other = Client(name="别家机构", industry="medical_beauty", contact=None, plan="free")
    db.add(other)
    db.commit()
    db.add(Script(client_id=other.id, content="别家机构的违规话术内容", status="pending"))
    db.commit()

    shop = _register(client, "shop_iso", "merchant", "隔离测试机构")
    listed = client.get(f"{API}/scripts", headers=shop["headers"])
    assert listed.status_code == 200
    assert listed.json()["total"] == 0, "商家不应看到别家机构的话术"


def test_merchant_write_forces_own_client(client: TestClient) -> None:
    """商家提交别家 client_id 必须被强制改回自己的机构。"""
    shop = _register(client, "shop_force", "merchant", "强制归属机构")
    own = shop["user"]["client_id"]

    created = client.post(f"{API}/scripts", headers=shop["headers"],
                          json={"client_id": 999999, "content": "试图写进别人的机构"})
    assert created.status_code == 200, created.text
    assert created.json()["data"]["client_id"] == own


def test_merchant_cannot_read_other_audit(client: TestClient, auth_headers: dict, db) -> None:
    """越权读单条资源按 404 处理，不泄漏资源是否存在。"""
    from backend.db.models import Audit, Client, Script

    other = Client(name="审计越权机构", industry="medical_beauty", contact=None, plan="free")
    db.add(other)
    db.commit()
    script = Script(client_id=other.id, content="别人的话术内容足够长", status="audited")
    db.add(script)
    db.commit()
    audit = Audit(script_id=script.id, score=0, hit_count=0, incomplete=False,
                  latency_ms=1, model="test")
    db.add(audit)
    db.commit()

    shop = _register(client, "shop_audit", "merchant", "审计越权测试")
    resp = client.get(f"{API}/audits/{audit.id}", headers=shop["headers"])
    assert resp.status_code == 404


def test_batch_audit_rejects_cross_tenant_script(client: TestClient, auth_headers: dict, db) -> None:
    """批量审查里混入别家话术要整批拒绝，避免被当成探测手段。"""
    from backend.db.models import Client, Script

    other = Client(name="批量越权机构", industry="medical_beauty", contact=None, plan="free")
    db.add(other)
    db.commit()
    foreign = Script(client_id=other.id, content="别家机构的待审话术内容", status="pending")
    db.add(foreign)
    db.commit()

    shop = _register(client, "shop_batch", "merchant", "批量越权测试")
    resp = client.post(f"{API}/audit/batch", headers=shop["headers"],
                       json={"client_id": shop["user"]["client_id"],
                             "script_ids": [foreign.id]})
    assert resp.status_code == 404


def test_batch_audit_validates_size(client: TestClient) -> None:
    """上限 20 条：再多会让浏览器超时，明确拒绝而不是假装很快。"""
    shop = _register(client, "shop_size", "merchant", "上限校验机构")
    resp = client.post(f"{API}/audit/batch", headers=shop["headers"],
                       json={"client_id": shop["user"]["client_id"],
                             "script_ids": list(range(1, 22))})
    # 参数校验错误由全局处理器统一映射为 400（与其它接口口径一致）
    assert resp.status_code == 400


def test_daily_report_is_scoped_for_merchant(client: TestClient, auth_headers: dict, db) -> None:
    """商家日报只统计自己机构：不能从平台汇总里读出同行规模。"""
    from datetime import date

    from backend.db.models import Audit, Client, Script

    other = Client(name="日报隔离机构", industry="medical_beauty", contact=None, plan="free")
    db.add(other)
    db.commit()
    script = Script(client_id=other.id, content="日报隔离测试话术内容", status="audited")
    db.add(script)
    db.commit()
    db.add(Audit(script_id=script.id, score=0, hit_count=1, incomplete=False,
                 latency_ms=1, model="test"))
    db.commit()

    shop = _register(client, "shop_report", "merchant", "日报隔离测试")
    resp = client.get(f"{API}/reports/daily",
                      params={"date": date.today().isoformat()}, headers=shop["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total"] == 0, "商家日报不应统计别家机构的审查"


def test_merchant_blocked_from_redteam_apis(client: TestClient) -> None:
    """红队相关的四个接口必须在 API 层就挡住商家账号。

    起因是一次无头预检：商家 token 直接请求 /redteam/options 拿到 200，
    而它的响应体里带着每条轴的 pattern / law_article / detector / version——
    等于把判定规则本身交给被审查方。前端菜单藏起来不算数，
    能被直接 curl 到的接口才是真实攻击面。
    """
    shop = _register(client, "shop_redteam_api", "merchant", "压测越权面")
    headers = shop["headers"]

    for path in (f"{API}/redteam/options", f"{API}/redteam/rt_none/gaps",
                 f"{API}/reports/redteam/rt_none"):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 403, f"{path} 竟然对商家开放"
        assert "管理员" in resp.json()["msg"]

    run = client.post(f"{API}/redteam/run", headers=headers,
                      json={"client_id": shop["user"]["client_id"],
                            "scenes": ["双眼皮"], "axes": ["efficacy_claim"]})
    assert run.status_code == 403, "压测会消耗模型额度并生成违规样本，不能由商家发起"
