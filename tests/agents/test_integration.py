"""D3 适配器与真实测试库集成；网络边界注入确定性响应。"""
import json
from decimal import Decimal

import pytest


def test_chat_adapter_uses_reported_usage_and_decimal_prices(monkeypatch):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, "llm_config", lambda: {
        "JUDGE_MODEL": "test-model", "JUDGE_INPUT_PRICE_PER_MILLION": "2",
        "JUDGE_OUTPUT_PRICE_PER_MILLION": "8"})
    calls = []

    def transport(path, payload):
        calls.append((path, payload))
        return {"choices": [{"message": {"content": '{"hits":[]}'}}],
                "model": "test-model", "usage": {"prompt_tokens": 125, "completion_tokens": 25}}

    result = audit_tool.UrllibChatModel(transport=transport).complete(
        [{"role": "user", "content": "test"}])
    assert result["cost"] == Decimal("0.00045")
    assert result["prompt_tokens"] == 125
    assert calls[0][0] == "/chat/completions"
    assert calls[0][1]["model"] == "test-model"
    assert result["content"] == '{"hits":[]}'


def test_missing_usage_is_not_fabricated(monkeypatch):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, "llm_config", lambda: {})
    model = audit_tool.UrllibChatModel(transport=lambda *args: {
        "choices": [{"message": {"content": "{}"}}]})
    with pytest.raises(KeyError):
        model.complete([])


def test_run_persists_metadata_and_recheck_does_not_write(db):
    from backend.db.models import Client, Script, Rule, Audit
    from backend.crud.audit import AuditRepository
    from backend.tools.audit_tool import AuditTool
    from backend.agents.base import ChatModel
    from sqlalchemy import select, func

    class FakeModel(ChatModel):
        def complete(self, messages):
            payload = ({"rewrites": ["请到院咨询适宜方案", "请咨询专业医师"]}
                       if "改写" in messages[0]["content"] else {"hits": []})
            return dict(content=json.dumps(payload), model="fake",
                        prompt_tokens=10, completion_tokens=2, cost=Decimal("0.0001"))

    institution = Client(name="D3测试")
    db.add(institution)
    db.flush()
    script = Script(client_id=institution.id, content="本院提供最高级服务")
    db.add_all([script, Rule(axis="absolute_terms", law_article="广告法第9条",
        pattern="绝对化用语", level="hard", detector="regex", exemptions=None),
        Rule(axis="efficacy_claim", law_article="广告法第9条", pattern="功效断言",
             level="hard", detector="llm_judge", exemptions=None)])
    db.commit()
    law = dict(code="广告法第9条", text="广告不得使用最高级用语。", source="测试法条")
    tool = AuditTool(repository=AuditRepository(db), model=FakeModel(),
                     search_law=lambda *args, **kwargs: [law])
    result = tool.run_audit(script.id, institution.id)
    saved = db.get(Audit, result["id"])
    assert saved.score == result["score"] == 0
    assert saved.hit_count == 1
    assert saved.hits_json[0]["status"] == "active"
    assert saved.law_refs_json
    assert saved.prompt_tokens == 10
    assert saved.completion_tokens == 2
    assert saved.cost == Decimal("0.0001")
    assert saved.model is not None
    assert saved.latency_ms >= 0
    assert "不构成法律意见" in result["disclaimer"]
    tool.recheck("本院提供最高级服务", institution.id)
    assert db.scalar(select(func.count()).select_from(Audit)) == 1
    db.refresh(script)
    assert script.status == "audited"
    rewritten = tool.rewrite_audit(result["id"])
    assert rewritten["rewrite_passed"] is True
    assert "不构成法律意见" in rewritten["disclaimer"]
    db.refresh(saved)
    assert saved.rewritten_text == "请到院咨询适宜方案"
    assert saved.rewrite_passed is True
    assert saved.cost == Decimal("0.0004")


def test_audit_routes_require_authentication(client):
    assert client.post("/api/v1/audit/run", json={"script_id": 1, "client_id": 1}).status_code == 401
    assert client.post("/api/v1/audit/1/rewrite").status_code == 401


def test_audit_routes_validate_and_call_tool(client, auth_headers, monkeypatch):
    import backend.api.v1.ai as routes
    from backend.core.config import DISCLAIMER_TEXT

    class Tool:
        def run_audit(self, script_id, client_id):
            return dict(id=7, score=2, disclaimer=DISCLAIMER_TEXT)

        def rewrite_audit(self, audit_id):
            return dict(id=audit_id, rewrite_passed=True, disclaimer=DISCLAIMER_TEXT)

    monkeypatch.setattr(routes, "build_audit_tool", lambda session: Tool())
    assert client.post("/api/v1/audit/run", headers=auth_headers,
                       json={"script_id": 0, "client_id": 1}).status_code == 400
    response = client.post("/api/v1/audit/run", headers=auth_headers,
                           json={"script_id": 1, "client_id": 1})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == 7
    response = client.post("/api/v1/audit/7/rewrite", headers=auth_headers)
    assert response.json()["data"]["rewrite_passed"] is True


def test_production_chat_transport_uses_chat_config_not_embedding(monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from backend.tools import audit_tool
    from backend.rag import embedding

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path, self.headers.get("Authorization"),
                             json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": '{"hits":[]}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1}}).encode())

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(audit_tool, "llm_config", lambda: {
        "JUDGE_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
        "JUDGE_API_KEY": "local-test-key", "JUDGE_MODEL": "chat-test"})
    monkeypatch.setattr(embedding, "llm_config", lambda: {"EMBEDDING_MODEL": "unrelated-model"})
    try:
        result = audit_tool.UrllibChatModel().complete([{"role": "user", "content": "审查"}])
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert requests[0][0] == "/v1/chat/completions"
    assert requests[0][1] == "Bearer local-test-key"
    assert requests[0][2]["model"] == "chat-test"
    assert result["prompt_tokens"] == 3
    assert result["pricing_source"] == "default_zero_estimate"
    assert "local-test-key" not in str(result)


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity"])
def test_chat_adapter_rejects_invalid_prices(monkeypatch, price):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, "llm_config", lambda: {
        "JUDGE_INPUT_PRICE_PER_MILLION": price})
    with pytest.raises(ValueError, match="报价"):
        audit_tool.UrllibChatModel(transport=lambda *args: {})


def test_authenticated_api_persists_and_mcp_rechecks_same_pipeline(db, client, auth_headers, monkeypatch):
    from sqlalchemy import func, select
    from backend.api.v1 import ai
    from backend.db.models import Audit, Client, Rule, Script
    from backend.tools import audit_tool
    from backend.mcp_server.server import audit_recheck

    institution = Client(name="API完整路径")
    db.add(institution)
    db.flush()
    script = Script(client_id=institution.id, content="本院提供最高级服务")
    db.add_all([script, Rule(axis="absolute_terms", law_article="广告法第9条",
        pattern="绝对化用语", level="hard", detector="regex")])
    db.commit()
    law = dict(code="广告法第9条", text="不得使用最高级用语。", source="测试法条")
    factory = audit_tool.build_audit_tool
    build = lambda session: factory(session, model=object(), search_law=lambda query: [law])
    monkeypatch.setattr(ai, "build_audit_tool", build)
    response = client.post("/api/v1/audit/run", headers=auth_headers,
                           json={"script_id": script.id, "client_id": institution.id})
    assert response.status_code == 200
    result = response.json()["data"]
    db.expire_all()
    stored = db.get(Audit, result["id"])
    assert stored.score == result["score"] == 0
    assert stored.hits_json[0]["quote"] == "最高级"
    assert stored.law_refs_json == [law]
    monkeypatch.setattr(audit_tool, "build_audit_tool", build)
    checked = audit_recheck(script.content, institution.id)
    assert checked["score"] == result["score"]
    assert checked["hits"] == result["hits"]
    assert db.scalar(select(func.count()).select_from(Audit)) == 1
    assert client.post("/api/v1/audit/run", headers=auth_headers,
        json={"script_id": script.id, "client_id": institution.id + 999999}).status_code == 404
    assert client.post("/api/v1/audit/999999/rewrite", headers=auth_headers).status_code == 404
