"""法条追溯接口：命中条文（可精确到项）-> 该项原文 + 所属条全文。

这是「引文级可解释」的最后一公里：只给条号等于让用户自己翻法条；
而只给整条又会把「到底触发了哪一项」埋掉，所以接口支持 item_no 精确到项。
"""

from fastapi.testclient import TestClient


def test_find_law_article_returns_full_article() -> None:
    """不带项号时返回整条原文，并含该项切分所需的 article_text。"""
    from backend.rag.ingest import find_law_article

    found = find_law_article("医疗美容广告执法指南第5条")
    assert found is not None
    assert found["doc"] == "医疗美容广告执法指南"
    assert found["article_no"] == 5
    assert "容貌焦虑" in found["article_text"]
    assert found["item_text"] is None


def test_find_law_article_extracts_requested_item() -> None:
    """带项号时必须能切出该项，而不是把整条九项都返回。"""
    from backend.rag.ingest import find_law_article

    found = find_law_article("医疗美容广告执法指南第5条", "第五条(五)")
    assert found is not None
    assert found["item_text"] is not None
    assert found["item_text"].lstrip().startswith("（五）")
    # 只含本项内容：不应把第（六）项一起带出来。
    assert "推荐官" in found["article_text"]
    assert "推荐官" not in found["item_text"]
    assert "利用行业协会" in found["item_text"]


def test_extract_item_handles_unknown_label() -> None:
    """项号不存在时返回 None，由前端退化为整条展示，不编造内容。"""
    from backend.rag.ingest import extract_item

    assert extract_item("五、总则\n（一）甲；\n（二）乙。", "第五条(九)") is None
    assert extract_item("五、总则", None) is None


def test_find_law_article_unknown_returns_none() -> None:
    """未收录条文返回 None，由接口层转 404，不允许编造条文。"""
    from backend.rag.ingest import find_law_article

    assert find_law_article("不存在的法第99条") is None


def test_law_article_api_requires_auth(client: TestClient) -> None:
    """未认证不得读取（与其他业务接口一致）。"""
    assert client.get("/api/v1/law/article", params={"code": "广告法第16条"}).status_code != 200


def test_law_article_api_ok_with_item(client: TestClient, auth_headers: dict) -> None:
    """认证后：带项号返回该项原文；不带项号返回整条；未收录 404。"""
    resp = client.get("/api/v1/law/article",
                      params={"code": "广告法第16条", "item_no": "第十六条(一)"},
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["doc"] == "广告法"
    assert data["item_no"] == "第十六条(一)"
    assert data["item_text"].lstrip().startswith("（一）")
    assert "表示功效、安全性的断言或者保证" in data["item_text"]
    assert "说明治愈率或者有效率" in data["article_text"]

    whole = client.get("/api/v1/law/article", params={"code": "广告法第16条"}, headers=auth_headers)
    assert whole.status_code == 200
    assert whole.json()["data"]["item_text"] is None

    miss = client.get("/api/v1/law/article", params={"code": "不存在的法第99条"}, headers=auth_headers)
    assert miss.status_code == 404
    assert "未收录" in miss.json()["msg"]
