"""T2 整篇复核：处置权在代码，模型只能举证。

这几条用例守的不是"复核有没有效果"，而是**复核不能越权**：
越界 verdict、错引 quote、JSON 不可解析、调用直接炸——四种情况下都必须
"保持原判 + 留下痕迹"，绝不能出现"模型没结论 → 当合规放行"。
"""

import json

import pytest

from backend.agents.audit.recheck import hit_context, recheck_hits


class FakeModel:
    """按预置内容返回复核结论；记录调用次数以证明"没命中就不调用"。"""

    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        return dict(content=self.content, model="fake-recheck",
                    prompt_tokens=100, completion_tokens=20, cost=0.001)


def _result(hits):
    return dict(hits=hits, traces=[], prompt_tokens=0, completion_tokens=0, cost=0.0,
                timings_ms={})


def _hit(quote="永久", severity="hard", **extra):
    return dict(quote=quote, original_quote=quote, axis="absolute_terms",
                pattern="绝对化用语", law_article="广告法第九条", severity=severity,
                reason="命中永久", **extra)


def verdicts(rows):
    return json.dumps({"verdicts": rows}, ensure_ascii=False)


def test_confirm_keeps_original_verdict_and_charges_usage() -> None:
    """confirm 保持原判，但复核这一次调用的 token 与费用必须并入本条总账。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(verdicts([
        dict(index=0, quote="永久", verdict="confirm", reason="上下文明确在向顾客打包票")])),
        "效果永久", hits, result)
    assert kept == hits and kept[0]["severity"] == "hard"
    assert result["prompt_tokens"] == 100 and result["completion_tokens"] == 20
    assert result["recheck_model"] == "fake-recheck"
    assert "recheck" in result["timings_ms"]


def test_downgrade_softens_hard_hit_with_context_reason() -> None:
    """downgrade：hard→soft，写 downgrade_reason，且标记是复核给的（可区分来源）。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(verdicts([
        dict(index=0, quote="永久", verdict="downgrade", reason="一般规律陈述，非个体承诺")])),
        "效果永久", hits, result)
    assert kept[0]["severity"] == "soft"
    assert kept[0]["context_downgraded"] is True
    assert "整篇复核降级" in kept[0]["downgrade_reason"]


def test_dismiss_is_removed_but_kept_in_traces() -> None:
    """dismiss 从 active 命中移除，但必须在 traces 留痕——丢弃不留痕就没法审计和回补规则。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(verdicts([
        dict(index=0, quote="永久", verdict="dismiss", reason="否定结构：不是永久性")])),
        "效果可能不是永久性的", hits, result)
    assert kept == []
    assert result["context_dismissed"] is True
    marked = [t for t in result["traces"] if t["status"] == "dismissed_by_context"]
    assert marked and marked[0]["items"][0]["reason"] == "否定结构：不是永久性"


def test_out_of_range_verdict_is_not_adopted() -> None:
    """模型给白名单外的 verdict（比如 score=2）→ 不采纳，保持原判并记 recheck_rejected。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(verdicts([
        dict(index=0, quote="永久", verdict="acquit", reason="我觉得合规了")])),
        "效果永久", hits, result)
    assert kept == hits and kept[0]["severity"] == "hard"
    assert any(t["status"] == "recheck_rejected" for t in result["traces"])


def test_mismatched_quote_is_not_adopted() -> None:
    """quote 对不上就是模型在说别的话：不采纳，也不许借机改动严重度。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(verdicts([
        dict(index=0, quote="这句原文里根本没有", verdict="dismiss", reason="编造")])),
        "效果永久", hits, result)
    assert kept == hits
    assert not any(t["status"] == "dismissed_by_context" for t in result["traces"])


def test_index_out_of_bounds_is_ignored() -> None:
    """序号越界：不崩、不采纳、也不误删任何命中。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(verdicts([
        dict(index=7, quote="永久", verdict="dismiss", reason="乱序")])),
        "效果永久", hits, result)
    assert kept == hits


def test_model_failure_keeps_original_verdict() -> None:
    """复核调用失败：保持原判 + 记 recheck_failed，不能因为复核挂了就把命中当不存在。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(error=RuntimeError("网络超时")), "效果永久", hits, result)
    assert kept == hits and kept[0]["severity"] == "hard"
    assert any(t["status"] == "recheck_failed" for t in result["traces"])


def test_unparseable_response_keeps_original_verdict() -> None:
    """返回不是约定 JSON：同样保持原判并留痕，绝不静默当成无违规。"""
    hits = [_hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(content="复核完成，没有问题"), "效果永久", hits, result)
    assert kept == hits
    assert any(t["status"] == "recheck_unparseable" for t in result["traces"])


def test_no_hits_means_no_extra_call() -> None:
    """没命中就不花这次调用：复核只为已有命中的条目存在（成本控制）。"""
    model = FakeModel(verdicts([]))
    assert recheck_hits(model, "正常文案", [], _result([])) == []
    assert model.calls == 0


def test_agent_only_rechecks_ambiguous_hits() -> None:
    """接入层的"有信号才复核"必须由用例钉住：这是时延与费用的闸门。

    无信号 → 跳过并记 recheck_skipped；
    有 negated_suspected / context_hedge / needs_recheck 任一 → 发起复核。
    """
    from backend.agents.compliance import ComplianceAuditAgent

    def agent(model):
        return ComplianceAuditAgent(lambda: [], lambda q: [], model, detectors={})

    clean = [{"quote": "最高级", "severity": "hard", "axis": "absolute_terms"}]
    result = _result(clean)
    outcome = agent(FakeModel(verdicts([])))._recheck("本院提供最高级服务", clean, result)
    assert outcome == clean and result["recheck_skipped"] == "no_context_signal"

    marked = [{"quote": "永久", "severity": "soft", "axis": "absolute_terms",
               "negated_suspected": True}]
    result2 = _result(marked)
    model = FakeModel(verdicts([dict(index=0, quote="永久", verdict="confirm",
                                     reason="上下文确为卖点")]))
    agent(model)._recheck("效果不是永久的", marked, result2)
    assert model.calls == 1, "有语境信号必须送复核，否则 T1 的标记就是空转"


def test_identical_hits_are_dismissed_one_by_index_not_both() -> None:
    """两条字段完全相同的命中，dismiss 一条时另一条必须还在。

    用 `hit not in dismissed` 这类按相等筛选的写法会把两条一起删掉，
    表现出来是凭空少报一条违规——这种缺陷没有任何报错，只能靠用例钉住。
    """
    hits = [_hit(), _hit()]
    result = _result(hits)
    kept = recheck_hits(FakeModel(verdicts([
        dict(index=0, quote="永久", verdict="dismiss", reason="否定语境")])),
        "效果永久", hits, result)
    assert len(kept) == 1


def test_hit_context_falls_back_when_quote_absent() -> None:
    """定位不到引文时回退整篇开头，而不是给一个错位的窗口。"""
    assert hit_context("完整的一段原文内容", _hit(quote="不存在的片段"), window=4) == "完整的一段原文内"
    # 引文在原文明确定位：窗口 = 前 4 字 + 引文本身 + 后 4 字
    assert hit_context("磨皮效果可能不是永久性的", _hit(quote="永久"), window=4) == "可能不是永久性的"
