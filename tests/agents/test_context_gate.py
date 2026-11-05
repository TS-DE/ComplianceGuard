"""T1 语境闸：否定 / 假设-引用-科普 语境只标记，标记改变分级而不改变命中存废。

这里刻意覆盖三层，缺一层都可能让"断章取义"悄悄回来：
1. 装饰器层：确定性命中确实带上标记（且不丢弃命中）；
2. 窗口层：否定词隔了一句就不算——否则"你会不会后悔？保证一次见效"会被放行；
3. 分级闸层：否定标记必须**排在承诺词判断之前**，不然 `永久` 这类
   "既是命中词又是承诺词"的情况永远降不下来（这正是原始缺陷）。
"""

import pytest

from backend.agents.base import (
    DETECTORS, ContextGateDetector, KeywordDetector, RegexDetector, mark_hit_context)
from backend.agents.compliance import downgrade_descriptive_hits


def _rule(axis="absolute_terms", level="hard", expression=None, keywords=()):
    from backend.agents.base import Rule

    return Rule(axis=axis, law_article="广告法第九条", pattern="绝对化用语",
                level=level, detector="regex", expression=expression, keywords=keywords)


def test_negation_left_of_hit_is_marked_not_dropped() -> None:
    """「可能不是永久性的」：命中仍在，但打上否定嫌疑——丢弃命中会把真违规一起吞掉。"""
    text = "磨皮术的效果可能不是永久性的"
    hits = DETECTORS["regex"].detect(text, _rule())
    assert [hit["quote"] for hit in hits] == ["永久"]
    assert hits[0]["negated_suspected"] is True
    assert hits[0]["negation_signal"] == "不是"
    assert hits[0]["severity"] == "hard", "检测层不改严重度，分级是分级闸的事"


def test_detector_classes_themselves_stay_pure() -> None:
    """裸 RegexDetector 不加标记：语境层是装饰器的职责，内层保持可单独复用（SRP/LSP）。"""
    assert "negated_suspected" not in RegexDetector().detect("可能不是永久", _rule())[0]
    assert isinstance(DETECTORS["regex"], ContextGateDetector)


def test_negation_across_sentence_boundary_does_not_excuse() -> None:
    """否定词隔了一句，不能救下本句的承诺——这是窗口的全部意义。"""
    text = "不用担心。效果永久"
    hit = DETECTORS["regex"].detect(text, _rule())[0]
    assert "negated_suspected" not in hit


def test_hypothesis_context_in_same_sentence_is_marked() -> None:
    """假设语境在同句内即标记；只标记，不擅自放行。"""
    text = "如果不做术后护理，效果永久"
    hit = DETECTORS["regex"].detect(text, _rule())[0]
    assert hit["context_hedge"] is True
    assert hit["context_signal"] == "如果"
    assert "negated_suspected" not in hit


def test_popular_science_signal_marks_sentence() -> None:
    """科普语境信号来自同句，而不是整篇——一篇科普文里插一句承诺不该整条放行。"""
    text = "科普一下：激光能不能永久脱毛。"
    hits = DETECTORS["regex"].detect(text, _rule())
    assert hits and all(hit["context_hedge"] for hit in hits)


def test_unmarkable_hit_is_left_untouched() -> None:
    """命中片段在归一文本里找不到时不标记，宁缺毋错（交给复核判断）。"""
    hit = mark_hit_context("完全不同的原文", {"quote": "永久"})
    assert "negated_suspected" not in hit and "context_hedge" not in hit


def test_keyword_detector_also_gets_the_gate() -> None:
    """装饰器同时套在 keyword 上：否定语境不是正则专属。"""
    rule = _rule(axis="efficacy_claim", keywords=("保证",))
    hits = DETECTORS["keyword"].detect("我们不保证效果", rule)
    assert hits[0]["negated_suspected"] is True


def test_gate_downgrades_negated_hit_before_commitment_check() -> None:
    """核心回归：`永久` 既是命中词又是承诺词，否定标记必须赢过承诺词判断。"""
    hits = [{"quote": "永久", "severity": "hard", "negated_suspected": True,
             "negation_signal": "不是"}]
    result = downgrade_descriptive_hits(hits)
    assert result[0]["severity"] == "soft"
    assert result[0]["downgraded"] is True
    assert result[0]["needs_recheck"] is True
    assert "否定" in result[0]["downgrade_reason"]


def test_gate_still_hardens_real_commitment() -> None:
    """反面对照：没有否定的"保证"必须仍是硬违规，否则 T1 就成了放行开关。"""
    hits = [{"quote": "保证三个月恢复正常肤色", "severity": "hard"}]
    assert downgrade_descriptive_hits(hits)[0]["severity"] == "hard"


def test_hedge_only_hit_is_marked_for_recheck_without_downgrade() -> None:
    """只有假设语境、词表看不出限定：留 needs_recheck，不擅自降级（避免"科普"救下真违规）。"""
    hits = [{"quote": "永久", "severity": "hard", "context_hedge": True}]
    result = downgrade_descriptive_hits(hits)
    assert result[0]["severity"] == "hard"
    assert result[0]["needs_recheck"] is True


def test_wrapping_does_not_swallow_inner_errors() -> None:
    """装饰器不改变内层异常语义：未预编译表达式照样抛 KeyError（LSP）。"""
    from backend.agents.base import Rule

    with pytest.raises(KeyError):
        DETECTORS["regex"].detect("原文", Rule(axis="unprepared", expression="new"))
