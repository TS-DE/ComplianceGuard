"""确定性命中（regex/keyword）必须送整篇复核——"断章取义"结构性缺口的回归用例。

根因：路线A 首 call 带全文后，复核整段被跳过（context_in_first_call）。
但 regex/keyword 只做 finditer，从来没看过上下文；
「以预防皮肤长久或永久变色」里的"永久"因此以绝对化用语硬违规结案。
"""

import json

from backend.agents.compliance import ComplianceAuditAgent


class FakeModel:
    """按预置 verdict 返回；记录收到的复核条目。"""

    def __init__(self, rows):
        self.rows, self.seen = rows, []

    def complete(self, messages):
        payload = json.loads(messages[1]["content"])
        self.seen.append(payload)
        return dict(content=json.dumps({"verdicts": self.rows}, ensure_ascii=False),
                    model="fake", prompt_tokens=10, completion_tokens=2, cost=0.0)


def _result():
    return dict(traces=[], prompt_tokens=0, completion_tokens=0, cost=0.0, timings_ms={})


def _agent(model):
    return ComplianceAuditAgent(lambda: [], lambda q: [], model, detectors={})


def _coded(quote="永久"):
    return dict(quote=quote, original_quote=quote, axis="absolute_terms", detector="regex",
                severity="hard", needs_recheck=True)


def _judged(quote="保证一次见效"):
    return dict(quote=quote, original_quote=quote, axis="efficacy_claim",
                detector="llm_judge", severity="hard")


def test_only_llm_hits_may_skip_with_context() -> None:
    """全部来自 llm_judge 且有上下文 → 才允许 context_in_first_call。"""
    model = FakeModel([])
    hits = [_judged()]
    result = _result()
    assert _agent(model)._recheck("保证一次见效", hits, result, context="全文") == hits
    assert result["recheck_skipped"] == "context_in_first_call"
    assert model.seen == []


def test_coded_hit_is_rechecked_even_with_context() -> None:
    """存在 regex 命中时必须复核，且只送确定性命中、整篇文本作为全文。"""
    text = "保护皮肤免受日光照射 6 到 12 个月，以预防皮肤长久或永久变色。"
    model = FakeModel([dict(index=0, quote="永久", verdict="dismiss", reason="修饰风险后果")])
    hits = [_coded(), _judged("应更显光滑")]
    result = _result()
    kept = _agent(model)._recheck(text, hits, result, context="整篇素材：" + text)
    assert "recheck_skipped" not in result
    assert [item["quote"] for item in model.seen[0]["items"]] == ["永久"]
    assert model.seen[0]["full_text"].startswith("整篇素材")
    assert [hit["quote"] for hit in kept] == ["应更显光滑"]
    verdicts = [t for t in result["traces"] if t["status"] == "recheck_verdicts"]
    assert verdicts and verdicts[0]["items"][0]["verdict"] == "dismiss"


def test_confirm_keeps_coded_hard_hit_and_leaves_trace() -> None:
    """复核确认 → 维持硬违规，且 trace 能看到 confirm（区别于"没复核"）。"""
    model = FakeModel([dict(index=0, quote="永久", verdict="confirm", reason="自我标榜效果")])
    hits = [_coded()]
    result = _result()
    kept = _agent(model)._recheck("永久有效，一次做完不再长", hits, result, context="全文")
    assert kept[0]["severity"] == "hard" and kept[0]["recheck_verdict"] == "confirm"
    assert any(t["status"] == "recheck_verdicts" for t in result["traces"])


def test_recheck_failure_keeps_coded_hit() -> None:
    """复核挂了不许放行：命中保留为硬违规。"""
    class Broken:
        def complete(self, messages):
            raise RuntimeError("timeout")

    hits = [_coded()]
    result = _result()
    kept = _agent(Broken())._recheck("效果永久", hits, result, context="全文")
    assert kept == hits and kept[0]["severity"] == "hard"
    assert any(t["status"] == "recheck_failed" for t in result["traces"])


def test_validate_marks_regex_hits_for_recheck() -> None:
    """端到端：regex 命中出口自带 needs_recheck，无上下文时也走复核而不是 no_context_signal。"""
    rules = [dict(axis="absolute_terms", detector="regex", level="hard",
                  law_article="广告法第9条(三)", pattern="绝对化用语")]
    law = [dict(code="广告法第9条(三)", text="广告不得使用最高级用语。", source="测试")]
    model = FakeModel([dict(index=0, quote="最高级", verdict="confirm", reason="自我标榜")])
    result = ComplianceAuditAgent(lambda: rules, lambda q: law, model).review("本院提供最高级服务")
    assert result["raw_hits"][0]["needs_recheck"] is True
    assert result.get("recheck_skipped") is None
    assert result["score"] == 0
