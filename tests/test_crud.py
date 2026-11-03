"""四套 CRUD 用例：增删改查、分页、过滤、404、409、401、业务校验。"""

import pytest
from fastapi.testclient import TestClient

API = "/api/v1"


def _create(client: TestClient, headers: dict, res: str, payload: dict) -> dict:
    resp = client.post(f"{API}/{res}", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


@pytest.fixture()
def seeded(client: TestClient, auth_headers: dict) -> dict:
    """一条 client -> script -> audit 链路。"""
    c = _create(client, auth_headers, "clients", {"name": "测试口腔"})
    s = _create(
        client, auth_headers, "scripts",
        {"client_id": c["id"], "content": "保证白三个色度", "scene": "美白"},
    )
    a = _create(client, auth_headers, "audits", {"script_id": s["id"], "score": 0})
    return {"client": c, "script": s, "audit": a}


@pytest.mark.parametrize("res", ["clients", "scripts", "audits", "rules"])
def test_list_requires_auth(client: TestClient, res: str) -> None:
    resp = client.get(f"{API}/{res}")
    assert resp.status_code == 401


@pytest.mark.parametrize("res", ["clients", "scripts", "audits", "rules"])
@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_id_404(client: TestClient, auth_headers: dict, res: str, method: str) -> None:
    kwargs = {"headers": auth_headers}
    if method == "put":
        kwargs["json"] = {}
    resp = getattr(client, method)(f"{API}/{res}/999999", **kwargs)
    assert resp.status_code == 404
    assert resp.json()["code"] == 404


def test_clients_full_crud(client: TestClient, auth_headers: dict) -> None:
    created = _create(client, auth_headers, "clients", {"name": "A 机构", "contact": "张三"})
    assert created["industry"] == "medical_beauty"
    assert created["plan"] == "free"
    cid = created["id"]

    got = client.get(f"{API}/clients/{cid}", headers=auth_headers).json()["data"]
    assert got["name"] == "A 机构"

    upd = client.put(f"{API}/clients/{cid}", json={"plan": "pro"}, headers=auth_headers)
    assert upd.json()["data"]["plan"] == "pro"
    assert upd.json()["data"]["name"] == "A 机构"  # 部分更新不动其它字段

    assert client.delete(f"{API}/clients/{cid}", headers=auth_headers).status_code == 200
    assert client.get(f"{API}/clients/{cid}", headers=auth_headers).status_code == 404


def test_pagination_shape(client: TestClient, auth_headers: dict) -> None:
    for i in range(5):
        _create(client, auth_headers, "clients", {"name": f"机构{i}"})
    body = client.get(f"{API}/clients?page=2&page_size=2", headers=auth_headers).json()
    assert set(body) == {"code", "msg", "data", "total"}
    assert body["total"] == 5
    assert len(body["data"]) == 2


def test_page_size_over_limit_400(client: TestClient, auth_headers: dict) -> None:
    resp = client.get(f"{API}/clients?page_size=101", headers=auth_headers)
    assert resp.status_code == 400


def test_scripts_filter_by_client(client: TestClient, auth_headers: dict, seeded: dict) -> None:
    other = _create(client, auth_headers, "clients", {"name": "其它机构"})
    _create(client, auth_headers, "scripts", {"client_id": other["id"], "content": "x"})
    cid = seeded["client"]["id"]
    body = client.get(f"{API}/scripts?client_id={cid}", headers=auth_headers).json()
    assert body["total"] == 1
    assert all(item["client_id"] == cid for item in body["data"])


def test_script_default_status_and_update(client: TestClient, auth_headers: dict, seeded: dict) -> None:
    sid = seeded["script"]["id"]
    assert seeded["script"]["status"] == "pending"
    resp = client.put(f"{API}/scripts/{sid}", json={"status": "audited"}, headers=auth_headers)
    assert resp.json()["data"]["status"] == "audited"


def test_script_unknown_client_422(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        f"{API}/scripts", json={"client_id": 999999, "content": "x"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_audits_filter_by_client(client: TestClient, auth_headers: dict, seeded: dict) -> None:
    cid = seeded["client"]["id"]
    body = client.get(f"{API}/audits?client_id={cid}", headers=auth_headers).json()
    assert body["total"] == 1
    assert body["data"][0]["score"] == 0
    empty = client.get(f"{API}/audits?client_id=999999", headers=auth_headers).json()
    assert empty["total"] == 0


@pytest.mark.parametrize("bad", [99, 3, -2])
def test_audit_invalid_score_rejected(client: TestClient, auth_headers: dict, seeded: dict, bad: int) -> None:
    resp = client.post(
        f"{API}/audits", json={"script_id": seeded["script"]["id"], "score": bad},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_db_check_constraint_blocks_bad_score(db, seeded: dict) -> None:
    """绕过 API 直写库也会被 ck_audits_score 拦住。"""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    with pytest.raises(OperationalError, match="ck_audits_score"):
        db.execute(
            text("INSERT INTO audits(script_id, score) VALUES (:s, 99)"),
            {"s": seeded["script"]["id"]},
        )
    db.rollback()


def test_delete_with_downstream_409(client: TestClient, auth_headers: dict, seeded: dict) -> None:
    cid, sid = seeded["client"]["id"], seeded["script"]["id"]
    assert client.delete(f"{API}/clients/{cid}", headers=auth_headers).status_code == 409
    assert client.delete(f"{API}/scripts/{sid}", headers=auth_headers).status_code == 409
    # 自下而上删除则全部成功
    aid = seeded["audit"]["id"]
    for res, rid in (("audits", aid), ("scripts", sid), ("clients", cid)):
        assert client.delete(f"{API}/{res}/{rid}", headers=auth_headers).status_code == 200


RULE = {"axis": "efficacy_claim", "law_article": "广告法第16条", "pattern": "保证功效", "level": "hard"}


def test_rule_create_and_bad_axis_422(client: TestClient, auth_headers: dict) -> None:
    created = _create(client, auth_headers, "rules", RULE)
    assert created["version"] == 1 and created["enabled"] is True
    resp = client.post(f"{API}/rules", json={**RULE, "axis": "not_an_axis"}, headers=auth_headers)
    assert resp.status_code == 422


def test_rule_content_change_bumps_version(client: TestClient, auth_headers: dict) -> None:
    """铁律 7：改内容 -> 新行 version+1，旧行停用保留。"""
    old = _create(client, auth_headers, "rules", RULE)
    new = client.put(
        f"{API}/rules/{old['id']}", json={"pattern": "保证/承诺功效"}, headers=auth_headers
    ).json()["data"]
    assert new["id"] != old["id"]
    assert new["version"] == 2
    kept = client.get(f"{API}/rules/{old['id']}", headers=auth_headers).json()["data"]
    assert kept["enabled"] is False and kept["pattern"] == "保证功效"


def test_rule_toggle_does_not_bump(client: TestClient, auth_headers: dict) -> None:
    old = _create(client, auth_headers, "rules", RULE)
    upd = client.put(
        f"{API}/rules/{old['id']}", json={"enabled": False}, headers=auth_headers
    ).json()["data"]
    assert upd["id"] == old["id"] and upd["version"] == 1 and upd["enabled"] is False


def test_scripts_content_search(client, auth_headers):
    root = '/api/v1'
    institution = client.post(root+'/clients', headers=auth_headers, json={'name':'搜索机构'}).json()['data']
    for content in ['双眼皮面诊限定词', '口腔咨询']:
        client.post(root+'/scripts', headers=auth_headers, json={'client_id':institution['id'],'content':content})
    result = client.get(root+'/scripts', headers=auth_headers, params={'q':'限定词'}).json()
    assert result['total'] == 1
    assert result['data'][0]['content'] == '双眼皮面诊限定词'
    assert client.get(root+'/scripts', headers=auth_headers, params={'q':'不存在'}).json()['total'] == 0
    assert client.get(root+'/scripts', headers=auth_headers).json()['total'] == 2
