"""D3 适配器与真实测试库集成；网络边界注入确定性响应。"""
import json
from decimal import Decimal

import pytest


def test_incomplete_cannot_persist_compliant_score(db):
    from backend.crud.audit import AuditRepository
    from backend.db.models import Client, Script, Audit
    institution = Client(name='未完成防线')
    db.add(institution)
    db.flush()
    script = Script(client_id=institution.id, content='介绍服务')
    db.add(script)
    db.commit()
    result = dict(score=2, incomplete=True, hit_count=0, hits=[], law_refs=[], model=None,
                  prompt_tokens=0, completion_tokens=0, cost=0, latency_ms=0)
    audit_id = AuditRepository(db).save(script.id, result)
    assert db.get(Audit, audit_id).score == -1


def test_chat_adapter_uses_reported_usage_and_decimal_prices(monkeypatch):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, "llm_config", lambda: {
        "JUDGE_MODEL": "test-model", "JUDGE_INPUT_PRICE_PER_M": "2",
        "JUDGE_OUTPUT_PRICE_PER_M": "8"})
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
    # T2 只复核"语境上有疑问"的命中。本句是无否定的常规绝对化用语，
    # 复核必须被跳过：多花一次调用不改变任何结论，却给单条加 2~12 秒。
    # 所以这里钉的是"跳没跳"这个设计，而不是钉一个调用次数——次数会随链路步骤变。
    assert "recheck" not in result["timings_ms"], "无语境信号不应发起整篇复核"
    assert result["recheck_skipped"] == "no_context_signal"
    assert saved.prompt_tokens == result["prompt_tokens"] == 10
    assert saved.completion_tokens == result["completion_tokens"] == 2
    assert saved.cost == result["cost"] == Decimal("0.0001")
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
    # 累计费用 = 首次审查 + 改写与二次过审（T2 之后二次过审内部还含整篇复核调用）。
    # 这里断言"落库账 = 两次上报之和"，不再钉死具体数字：链路的步数变了，账必须跟着变，
    # 但"少记一次调用"必须被这条断言抓到。
    assert saved.cost == result["cost"] + rewritten["cost"]
    assert saved.cost > result["cost"], "改写与复核的调用必须计入本条总账，不能只记首次"


def test_audit_routes_require_authentication(client):
    assert client.post("/api/v1/audit/run", json={"script_id": 1, "client_id": 1}).status_code == 401
    assert client.post("/api/v1/audit/1/rewrite").status_code == 401


def test_audit_routes_validate_and_call_tool(client, auth_headers, monkeypatch):
    import backend.api.v1.ai as routes
    from backend.core.config import DISCLAIMER_TEXT

    class Tool:
        seen = {}

        def run_audit(self, script_id, client_id):
            return dict(id=7, score=2, disclaimer=DISCLAIMER_TEXT)

        def rewrite_audit(self, audit_id, budget_seconds=None):
            # budget_seconds 是接口层传来的整次请求预算，打桩必须收下这个参数，
            # 否则路由改签名而测试仍绿，测的就不是真调用路径
            Tool.seen['budget'] = budget_seconds
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
    assert Tool.seen['budget'] == 90, "整次请求的默认预算必须由路由传到服务层，而不是各自取默认值"


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
    assert result["pricing_source"] == "unpriced"
    assert "local-test-key" not in str(result)


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity"])
def test_chat_adapter_rejects_invalid_prices(monkeypatch, price):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, "llm_config", lambda: {
        "JUDGE_INPUT_PRICE_PER_M": price})
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


def test_indexed_docs_creates_one_client(monkeypatch):
    import chromadb
    from types import SimpleNamespace
    from backend.tools.audit_tool import indexed_docs
    if hasattr(indexed_docs, 'cache_clear'):
        indexed_docs.cache_clear()
    calls = []
    collection = SimpleNamespace(get=lambda **kwargs: {
        'metadatas': [{'code': '广告法第9条'}, {'code': '医美指南第五条'}]})
    def client(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(get_collection=lambda name: collection)
    monkeypatch.setattr(chromadb, 'PersistentClient', client)
    try:
        first, second = indexed_docs(), indexed_docs()
        assert first == second == {'广告法', '医疗美容广告执法指南'}
        assert len(calls) == 1
        print(f'indexed_docs calls=2; PersistentClient creations={len(calls)}')
    finally:
        if hasattr(indexed_docs, 'cache_clear'):
            indexed_docs.cache_clear()


@pytest.mark.parametrize('judge_cost', [Decimal('0.001'), None])
def test_embedding_official_price_and_total(monkeypatch, judge_cost):
    from types import SimpleNamespace
    from backend.rag.embedding import usage_meter, record_usage, ROOT
    from dotenv import dotenv_values
    from backend.tools.audit_tool import AuditTool
    config = dotenv_values(ROOT / '.env.example')
    assert config.get('EMBEDDING_PRICE_PER_M') == '0.5'
    with usage_meter() as usage:
        record_usage('/embeddings', {'usage': {'total_tokens': 1000}}, config)
    assert usage['embedding']['cost'] == Decimal('0.000500')
    tool = AuditTool.__new__(AuditTool)
    tool.model = SimpleNamespace()
    def review(*args, **kwargs):
        record_usage('/embeddings', {'usage': {'total_tokens': 1000}}, config)
        return dict(cost=judge_cost, prompt_tokens=10, completion_tokens=2)
    tool.auditor = SimpleNamespace(review=review)
    tool.repository = SimpleNamespace(client=lambda _: True,
        script=lambda _: dict(client_id=1, content='固定测试'), save=lambda *args: 1)
    result = tool.run_audit(1, 1)
    assert result['embedding_cost'] == Decimal('0.000500')
    if judge_cost is None:
        assert result['total_cost'] is None
        assert '仅 embedding 已计价' in result['cost_note']
    else:
        assert result['total_cost'] == Decimal('0.001500')
    print(f"embedding_cost={result['embedding_cost']}; total_cost={result['total_cost']}; {result['cost_note']}")


@pytest.mark.parametrize('judge_cost', ['0.001', None])
def test_run_costs_note_tracks_embedding_pricing(judge_cost):
    from backend.tools.db_tool import RedteamRepository
    repo = RedteamRepository.__new__(RedteamRepository)
    repo.samples = lambda _: [dict(meta=dict(verdict='TN', cost_breakdown={
        'a1': dict(cost=judge_cost), 'rag_rewrite': dict(cost='0'),
        'embedding': dict(cost='0.000500', prompt_tokens=1000)}))]
    result = repo.run_costs('fixture')
    assert result['embedding_cost'] == Decimal('0.000500')
    assert 'embedding未计价' not in result['cost_note']
    if judge_cost is None:
        assert result['total_cost'] is None
        assert '仅 embedding 已计价' in result['cost_note']
    else:
        assert result['total_cost'] == Decimal('0.001500')
