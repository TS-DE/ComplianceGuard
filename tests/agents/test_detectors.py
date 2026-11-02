"""检测器契约：独立于数据库与真实模型。"""

import importlib
import json
from pathlib import Path
from dataclasses import asdict

import pytest

from backend.agents.base import ChatModel, Rule


class FakeModel(ChatModel):
    def __init__(self, content):
        self.content = content
        self.messages = []

    def complete(self, messages):
        self.messages = messages
        if isinstance(self.content, Exception):
            raise self.content
        return dict(content=self.content, model="fake", prompt_tokens=12,
                    completion_tokens=7, cost=0.02)


@pytest.mark.parametrize("rows", [[], [{"quote": "保证白3度", "law_article": "广告法第16条",
                                     "reason": "保证疗效", "severity": "soft", "pattern": "伪造", "score": 2}]])
def test_llm_returns_evidence_not_model_scores_and_includes_context(rows):
    from backend.agents.base import LLMJudgeDetector
    model = FakeModel(json.dumps({"hits": rows}, ensure_ascii=False))
    detector = LLMJudgeDetector(model)
    rule = Rule(axis="efficacy_claim", pattern="疗效保证", law_article="广告法第16条",
                law_refs=[{"code": "广告法第16条", "text": "不得作疗效保证"}],
                exemptions=[{"text": "示例豁免", "source": "指南"}], example_bad="保证变白")
    hits = detector.detect("保证白3度", rule)
    assert hits == ([dict(pattern="疗效保证", quote="保证白3度", severity="hard",
                          law_article="广告法第16条", detector="llm_judge", reason="保证疗效")] if rows else [])
    assert detector.last_usage == dict(model="fake", prompt_tokens=12, completion_tokens=7, cost=0.02)
    prompt = json.dumps(model.messages, ensure_ascii=False)
    assert all(value in prompt for value in ["不得作疗效保证", "示例豁免", "保证变白", "保证白3度"])
    assert "不得编造" in prompt


@pytest.mark.parametrize("axis,text,quotes", [
    ("absolute_terms", "顶级机构永久有效", ["顶级", "永久"]),
    ("false_quantify", "3天见效，一次搞定，百分百有效", ["3天见效", "一次搞定", "百分百有效"]),
    ("cure_rate", "治愈率高达 95%，有效率99%", ["治愈率高达 95%", "有效率99%"]),
    ("cure_rate", "十个人九个好", ["十个人九个好"]),
    ("absolute_terms", "按需就诊", []),
    ("false_quantify", "3天后复诊", []),
    ("cure_rate", "术后需要复诊", []),
])
def test_regex_understands_seed_descriptions(axis, text, quotes):
    from backend.agents.base import RegexDetector
    seeds = json.loads((Path(__file__).parents[2] / "data/seeds/rules.json").read_text(encoding="utf-8"))
    rule = Rule(**next(row for row in seeds["rules"] if row["axis"] == axis))
    assert [hit["quote"] for hit in RegexDetector().detect(text, rule)] == quotes


def test_custom_regex_is_prepared_before_detection(monkeypatch):
    import re
    from backend.agents.base import RegexDetector
    detector = RegexDetector(expressions={"custom": r"白\d+度"})
    rule = Rule(axis="custom", expression=r"白\d+度", detector="regex", level="soft")
    monkeypatch.setattr(re, "compile", lambda *args, **kwargs: pytest.fail("compile during detect"))
    assert detector.detect("能白3度", rule) == [dict(pattern="", quote="白3度", severity="soft",
                                                law_article="", detector="regex")]
    with pytest.raises(KeyError):
        detector.detect("anything", Rule(axis="unprepared", expression="new"))


@pytest.mark.parametrize("text, quotes", [("零风险且无副作用", ["零风险", "无副作用"]), ("请咨询医生", [])])
def test_keyword_uses_explicit_terms_and_preserves_metadata(text, quotes):
    from backend.agents.base import KeywordDetector
    rule = Rule(axis="custom", pattern="安全承诺", law_article="广告法第16条", detector="keyword",
                keywords=("零风险", "无副作用"))
    hits = KeywordDetector().detect(text, rule)
    assert hits == [dict(pattern=rule.pattern, quote=q, severity="hard",
                         law_article=rule.law_article, detector="keyword") for q in quotes]


@pytest.mark.parametrize("content", ["not JSON", "{}", '{"hits": null}', '{"hits": {}}',
                                    '{"hits": [{"quote": 42, "law_article": "law", "reason": "r"}]}'])
def test_llm_rejects_malformed_responses(content):
    from backend.agents.base import LLMJudgeDetector
    detector = LLMJudgeDetector(FakeModel(content))
    with pytest.raises((ValueError, TypeError, KeyError)):
        detector.detect("原文", Rule())
    assert detector.last_usage["prompt_tokens"] == 12


def test_llm_propagates_failure_and_clears_stale_usage():
    from backend.agents.base import LLMJudgeDetector
    model = FakeModel('{"hits": []}')
    detector = LLMJudgeDetector(model)
    detector.detect("原文", Rule())
    failure = TimeoutError("provider timeout")
    model.content = failure
    with pytest.raises(TimeoutError) as caught:
        detector.detect("原文", Rule())
    assert caught.value is failure
    assert detector.last_usage == {}


def test_registry_dispatches_custom_detector_and_rejects_unknown(monkeypatch):
    from backend.agents import DETECTORS, Detector
    class FakeDetector(Detector):
        def detect(self, text, rule):
            return [{"quote": text, "pattern": rule.pattern}]
    monkeypatch.setitem(DETECTORS, "fake", FakeDetector())
    rule = Rule(detector="fake", pattern="custom")
    assert DETECTORS[rule.detector].detect("原文", rule) == [{"quote": "原文", "pattern": "custom"}]
    with pytest.raises(KeyError):
        DETECTORS["unknown"]
    assert all(isinstance(DETECTORS[name], Detector) for name in ("keyword", "regex", "llm_judge"))
    with pytest.raises(RuntimeError, match="configured"):
        DETECTORS["llm_judge"].detect("原文", Rule())


def test_rule_defaults_are_isolated_and_abstractions_are_abstract():
    base = importlib.import_module("backend.agents.base")
    first, second = base.Rule(axis="custom"), base.Rule(axis="custom")
    first.law_refs.append({"code": "广告法第16条", "text": "依据"})
    assert second.law_refs == []
    assert asdict(first) | {"law_refs": []} == asdict(second)
    assert first.id is None and first.version == 1
    assert first.level == "hard" and first.detector == "llm_judge"
    with pytest.raises(TypeError):
        base.Detector()
    with pytest.raises(TypeError):
        base.ChatModel()
