"""判定与复核的 system prompt 禁止模型在 reason 里表达分级意见。

根因（audit=251）：旧提示词写「仍要返回命中并在 reason 注明"描述性表述、无承诺词"，
由系统分级为疑似风险」，模型把这句话当模板套用——哪怕句中根本没有模糊限定词
（「玻尿酸面膜能够起到补水保湿的作用」），reason 也复述"标注为疑似风险
（实际应视为合规的科普描述）"。代码判 hard、理由说应疑似：标签与理由互相矛盾。

修法只改提示词、不动链路：reason 只写事实依据；分级意见（应视为/疑似/建议/
实际上/可视为等）由系统决定，模型不得表达。本文件钉住两件事：
1. 三处 prompt（llm_judge 判定、merged 判定、整篇复核）都带显式禁令；
2. 诱发复述的旧模板句（"在 reason 注明/写明 …"）已从 prompt 中移除。
"""

import json

from backend.agents.base import ChatModel, LLMJudgeDetector, Rule, merged_judgment
from backend.agents.audit.recheck import SYSTEM_PROMPT as RECHECK_PROMPT

JUDGMENT_BANNED = ('应视为', '可视为', '疑似', '建议', '实际上')


class CapturingModel(ChatModel):
    def __init__(self, content):
        self.content, self.messages = content, []

    def complete(self, messages):
        self.messages = messages
        return dict(content=self.content, model="fake", prompt_tokens=1,
                    completion_tokens=1, cost=0.0)


def _rule(axis="efficacy_claim"):
    return Rule(axis=axis, pattern="对疗效作出保证性承诺", law_article="广告法第16条",
                law_refs=[{"code": "广告法第16条", "text": "不得作疗效保证"}],
                exemptions=[], example_bad="保证变白")


def test_llm_judge_prompt_forbids_opinion_in_reason() -> None:
    model = CapturingModel(json.dumps({"hits": []}, ensure_ascii=False))
    LLMJudgeDetector(model).detect("玻尿酸面膜能够起到补水保湿的作用", _rule())
    system = model.messages[0]["content"]
    assert '禁止在 reason 里表达判断或分级意见' in system
    assert all(w in system for w in JUDGMENT_BANNED)
    assert 'reason 只写事实依据' in system
    # 旧模板句必须消失：它是"复述提示词而非报告判断"的直接来源
    assert '在 reason 注明"描述性表述、无承诺词"' not in system


def test_merged_prompt_forbids_opinion_in_reason() -> None:
    model = CapturingModel(json.dumps({"efficacy_claim": []}, ensure_ascii=False))
    merged_judgment(model, "玻尿酸面膜能够起到补水保湿的作用", [_rule()],
                    [{"code": "广告法第16条", "chunk_id": "x", "text": "不得作疗效保证"}])
    system = model.messages[0]["content"]
    assert '禁止在 reason 里表达判断或分级意见' in system
    assert all(w in system for w in JUDGMENT_BANNED)
    assert 'reason 只写事实依据' in system
    assert '在reason里注明"描述性表述、无承诺词"' not in system
    # 带上下文时旧句「reason 必须写明"…为何仍构成违规"或"为何只是常规告知不构成违规"」
    # 同样在命令模型表态，必须换成事实性要求
    model2 = CapturingModel(json.dumps({"efficacy_claim": []}, ensure_ascii=False))
    merged_judgment(model2, "该句", [_rule()],
                    [{"code": "广告法第16条", "chunk_id": "x", "text": "正文"}],
                    context="整篇素材")
    system2 = model2.messages[0]["content"]
    assert '为何仍构成违规' not in system2
    assert '禁止在 reason 里表达判断或分级意见' in system2


def test_recheck_prompt_forbids_opinion_in_reason() -> None:
    assert '禁止在 reason 里表达判断或分级意见' in RECHECK_PROMPT
    assert all(w in RECHECK_PROMPT for w in JUDGMENT_BANNED)
    assert 'reason 只写事实依据' in RECHECK_PROMPT


def test_model_reason_flows_through_unmodified_but_severity_is_systems_call() -> None:
    """代码侧不变：模型 reason 原样留痕，但 hard/soft 只由规则与分级闸决定。

    即使模型在 reason 里自称"应视为疑似"，命中严重度仍按规则 level 落 hard——
    断言的是"两条路互不通信"中代码这条路没把模型的表态当输入。
    """
    opinion = "故返回命中并标注为疑似风险（实际应视为合规的科普描述）"
    model = CapturingModel(json.dumps(
        {"hits": [dict(quote="能够起到补水保湿的作用", law_article="广告法第16条",
                       reason=opinion)]}, ensure_ascii=False))
    hits = LLMJudgeDetector(model).detect("玻尿酸面膜能够起到补水保湿的作用", _rule())
    assert hits[0]["reason"] == opinion          # 原样留痕，不篡改证据
    assert hits[0]["severity"] == "hard"          # 分级与 reason 无关（规则 level）
    assert "soft" not in json.dumps(hits[0])
