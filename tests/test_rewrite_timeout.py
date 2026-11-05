"""D · 改写请求的整次时间预算（90 秒）与"不许返回半成品"。

要钉住的不是"有没有 timeout 这个字段"，而是三件容易各说各话的事：
1. 预算到了就**不再发起下一次模型调用**（继续重试才是 10 分钟假死的成因）；
2. 预算到了就**不写库**，商家看不到半篇改写稿，响应是明确的 504；
3. 预算用完必须**清掉**，否则同一个模型实例被下一个请求复用时，
   第二个请求会一进门就"超时"——这类跨请求残留最难查。
"""

import json
from decimal import Decimal

import pytest

from backend.agents.base import ChatModel
from backend.core.errors import DeadlineExceededError, ModelCallError
from backend.crud.audit import AuditRepository
from backend.db.models import Audit, Client, Rule, Script
from backend.tools.audit_tool import AuditTool, UrllibChatModel


class FakeModel(ChatModel):
    """按"改写"字样分流，与集成测试同一口径；calls 记录被调用了几次。"""

    def __init__(self, delay=0.0):
        self.calls = []
        self.deadline = None
        self.delay = delay

    def complete(self, messages):
        from time import sleep

        self.calls.append(messages)
        if self.delay:
            sleep(self.delay)
        payload = ({"rewrites": ["请到院咨询适宜方案"]} if "改写" in messages[0]["content"]
                   else {"hits": []})
        return dict(content=json.dumps(payload), model="fake", prompt_tokens=1,
                    completion_tokens=1, cost=Decimal("0.000001"))


def _tool(db, model):
    institution = Client(name="超时预算机构")
    db.add(institution)
    db.flush()
    script = Script(client_id=institution.id, content="本院提供最高级服务")
    db.add_all([script,
                Rule(axis="absolute_terms", law_article="广告法第9条", pattern="绝对化用语",
                     level="hard", detector="regex", exemptions=None),
                # 加一条 llm_judge 规则，逐稿复核才会真的打模型；只有一条 regex 规则时
                # 复核链路一次都不调用，"预算传给谁"就测不出来
                Rule(axis="efficacy_claim", law_article="广告法第16条", pattern="功效断言",
                     level="hard", detector="llm_judge", exemptions=None)])
    db.commit()
    tool = AuditTool(repository=AuditRepository(db), model=model,
                     search_law=lambda *a, **k: [dict(code="广告法第9条",
                                                      text="广告不得使用最高级用语。",
                                                      source="测试法条")])
    audit_id = tool.run_audit(script.id, institution.id)["id"]
    return tool, audit_id, institution


def test_deadline_stops_before_the_wire():
    """预算已过就不该再打网络：这条是"假死"与"及时失败"的分界。"""
    seen = []

    def transport(path, payload):
        seen.append(path)
        raise AssertionError('不该发出请求')

    model = UrllibChatModel(transport=transport)
    model.deadline = 0.0                      # perf_counter 不可能小于 0，等价于"预算已用尽"
    with pytest.raises(ModelCallError) as exc:
        model.complete([{'role': 'user', 'content': 'x'}])
    assert exc.value.kind == 'deadline_exceeded'
    assert seen == []


def test_langchain_backend_honours_the_same_deadline():
    """两个后端必须有同一条保护，否则切到 langchain 就把 90 秒上限弄丢了。"""
    from backend.model.langchain_model import LangChainChatModel

    class Client:
        def invoke(self, messages):
            raise AssertionError('不该发出请求')

    model = LangChainChatModel(client=Client())
    model.deadline = 0.0
    with pytest.raises(ModelCallError) as exc:
        model.complete([{'role': 'user', 'content': 'x'}])
    assert exc.value.kind == 'deadline_exceeded'


def test_rewrite_over_budget_returns_504_and_writes_nothing(db):
    """服务层把"预算用尽"翻成 504，且此时一次库都没写。

    这里刻意让模型直接抛 deadline_exceeded：预算算法属于适配器（下面单独测），
    服务层的考点是"映射成 504 + 不返回半成品"，不该靠 sleep 赌时序。
    """
    tool, audit_id, _ = _tool(db, FakeModel())
    before = db.get(Audit, audit_id)
    snapshot = (before.rewritten_text, before.rewrite_passed, before.cost)

    class OutOfBudget(FakeModel):
        def complete(self, messages):
            self.calls.append(messages)
            raise ModelCallError("模型调用超过总时间预算", "deadline_exceeded", 1)

    model = OutOfBudget()
    tool.model = tool.rewriter.model = tool.auditor.model = model
    with pytest.raises(DeadlineExceededError) as exc:
        tool.rewrite_audit(audit_id, budget_seconds=90)
    assert exc.value.code == 504
    assert "未产生结果" in str(exc.value)

    db.expire_all()
    after = db.get(Audit, audit_id)
    assert (after.rewritten_text, after.rewrite_passed, after.cost) == snapshot, \
        "超时不得留下半成品改写稿"


def test_remaining_budget_caps_the_single_call_timeout():
    """预算必须压到"这一次读超时"上，否则"单次很慢"这种情况仍是硬上限之外的洞。

    旧写法只在每次尝试前看一眼预算：一次 180 秒的阻塞读可以完整跑满，
    所谓 90 秒上限最坏变成 90 + 180 秒。
    """
    from time import perf_counter

    seen: list[str] = []

    def transport(path, payload):
        model.attempts_seen.append(model.attempt_timeout)
        seen.append(path)
        # attempt_limit=2 与 model_error 对超时类错误的映射一致，不在测试里自造语义
        raise ModelCallError("模拟读超时", "timeout", 2)

    model = UrllibChatModel(transport=transport)
    model.attempts_seen = []
    model.timeout = 180
    model.deadline = perf_counter() + 3
    with pytest.raises(ModelCallError):
        model.complete([{'role': 'user', 'content': 'x'}])
    assert len(seen) == 2, "超时类错误按既有语义重试两次"
    assert all(timeout <= 3 for timeout in model.attempts_seen), model.attempts_seen
    assert model.deadline is not None      # 适配器不清这个：预算的生命周期归服务层管


def test_budget_reaches_every_model_holder(db):
    """rewriter 与 auditor 用的是不同实例时，预算也必须各自生效。

    生产上三者现在是同一对象，只设 self.model 也能过测试——但那是在赌对象身份：
    哪天单独注入一个模型实例，90 秒上限就悄悄失效，而且没有任何报错。
    """
    seen = []

    class Watcher(FakeModel):
        def complete(self, messages):
            seen.append(self.deadline)
            return super().complete(messages)

    tool, audit_id, _ = _tool(db, FakeModel())
    rewriter_model, auditor_model = Watcher(), Watcher()
    tool.model, tool.rewriter.model, tool.auditor.model = Watcher(), rewriter_model, auditor_model
    result = tool.rewrite_audit(audit_id, budget_seconds=60)
    assert result["rewrite_passed"] is True
    assert len(seen) >= 2, "改写生成与逐稿复核都应看到预算"
    assert all(deadline is not None for deadline in seen)
    assert rewriter_model.deadline is None and auditor_model.deadline is None


def test_deadline_is_cleared_after_success(db):
    """预算是一次性的：留存在模型实例上会让下一个请求一进门就"超时"。"""
    model = FakeModel()
    tool, audit_id, _ = _tool(db, model)
    result = tool.rewrite_audit(audit_id, budget_seconds=60)
    assert result["rewrite_passed"] is True
    assert model.deadline is None


def test_deadline_is_cleared_after_failure(db):
    """异常路径同样必须清预算：成功路径上的清理谁都会写，出事时才见真章。"""
    class Boom(FakeModel):
        def complete(self, messages):
            raise ModelCallError("模拟供应商失败", "connection", 1)

    tool, audit_id, _ = _tool(db, FakeModel())
    tool.model = tool.rewriter.model = Boom()
    with pytest.raises(ModelCallError):
        tool.rewrite_audit(audit_id, budget_seconds=60)
    assert tool.model.deadline is None
