"""法条追溯接口：命中条文 -> 条文原文 + 所属法规全表。

这是「引文级可解释」的最后一公里：只给条号等于让用户自己翻法条，
因此必须能一键拿到原文，并且能在整部法规里定位到该条。
"""

from fastapi.testclient import TestClient


def test_find_law_article_returns_original_text() -> None:
    """已知条文必须返回原文与同法规条文表，供前端定位高亮。"""
    from backend.rag.ingest import find_law_article

    found = find_law_article("医疗美容广告执法指南第5条")
    assert found is not None
    assert found["doc"] == "医疗美容广告执法指南"
    assert found["article_no"] == 5
    # 原文必须包含该项的真实表述，不能是摘要或占位。
    assert "容貌焦虑" in found["text"]
    assert len(found["articles"]) >= 1
    assert all({"code", "article_no", "text"} <= set(row) for row in found["articles"])


def test_find_law_article_unknown_returns_none() -> None:
    """未收录条文返回 None，由接口层转 404，不允许编造条文。"""
    from backend.rag.ingest import find_law_article

    assert find_law_article("不存在的法第99条") is None


def test_law_article_api_requires_auth(client: TestClient) -> None:
    """未认证不得读取（与其他业务接口一致）。"""
    assert client.get("/api/v1/law/article", params={"code": "广告法第16条"}).status_code != 200


def test_law_article_api_ok_and_not_found(client: TestClient, auth_headers: dict) -> None:
    """认证后：命中 200 且含原文；未收录 404 且带明确提示。"""
    ok_resp = client.get("/api/v1/law/article", params={"code": "广告法第16条"}, headers=auth_headers)
    assert ok_resp.status_code == 200
    body = ok_resp.json()
    assert body["code"] == 200
    assert body["data"]["doc"] == "广告法"
    assert "医疗、药品、医疗器械广告不得含有下列内容" in body["data"]["text"]

    miss = client.get("/api/v1/law/article", params={"code": "不存在的法第99条"}, headers=auth_headers)
    assert miss.status_code == 404
    assert "未收录" in miss.json()["msg"]
