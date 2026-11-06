"""audit=257 错位回归：同一词出现多次时，每条命中必须用自己位置的上下文。

根因链（真实数据钉死）：RegexDetector.finditer 找到三个「永久」（129 预防变色 /
149 不是永久性 / 171 永久见效），但下游全部 `text.find(quote)` 定位——
find 永远返回第一处，三条命中共享 129 的语境窗口：
· 复核拿到的 context 全是"预防…永久变色"，confirm/dismiss 配错了人；
· mark_hit_context 给 171 也打上 149 的否定信号；
· 前端卡片显示"永久(129)"、上下文却是"永久见效"句。

修法：detect 带 detect_start/detect_end，_validate 用它算真实锚点；
mark_hit_context / hit_context 优先用 hit['start']，切片校验不过才退回 find。
"""
import json

from backend.agents.base import RegexDetector, Rule, mark_hit_context
from backend.agents.audit.recheck import hit_context

TEXT = ("保护皮肤免受日光照射 6 到 12 个月，以预防皮肤长久或永久变色。"
        "请记住，磨皮术的效果可能不是永久性的。"
        "保证三个月恢复正常肤色，一次做完永久见效。")


def _rule():
    seeds = json.loads(open("data/seeds/rules.json", encoding="utf-8").read())
    row = next(r for r in seeds["rules"] if r["axis"] == "absolute_terms")
    return Rule(**{k: v for k, v in row.items() if k in Rule.__dataclass_fields__})


def test_regex_hits_carry_distinct_positions():
    hits = RegexDetector().detect(TEXT, _rule())
    perm = [h for h in hits if h["quote"] == "永久"]
    assert len(perm) == 3, "三处「永久」必须各自成一条命中"
    starts = sorted(h["detect_start"] for h in perm)
    assert len(set(starts)) == 3, "同一词重复出现时锚点必须互不相同"
    for h in perm:
        assert TEXT[h["detect_start"]:h["detect_end"]] == "永久"


def test_hit_context_uses_own_start_not_first_find():
    """复核窗口按 start 取：三条命中看到三句不同的上下文。"""
    at_first = TEXT.index("或永久变色") + 1
    at_last = TEXT.index("永久见效")
    first = hit_context(TEXT, dict(original_quote="永久", start=at_first), window=20)
    last = hit_context(TEXT, dict(original_quote="永久", start=at_last), window=20)
    assert "预防皮肤长久" in first and "永久见效" not in first
    assert "永久见效" in last and "预防皮肤长久" not in last
    # start 与 quote 对不上（老数据/篡改）→ 退回 find，仍取第一处，不猜别处
    fallback = hit_context(TEXT, dict(original_quote="永久", start=0), window=8)
    assert "长久或永久变色" in fallback and "永久见效" not in fallback


def test_mark_hit_context_negation_signal_follows_position():
    """149 的「不是」否定信号不得配给 171 的命中——只属于它自己。"""
    at149 = TEXT.index("效果可能不是永久性") + len("效果可能不是")
    at171 = TEXT.index("一次做完永久见效") + len("一次做完")
    h1 = mark_hit_context(TEXT, dict(quote="永久", start=at149))
    h2 = mark_hit_context(TEXT, dict(quote="永久", start=at171))
    assert TEXT[at149:at149 + 2] == "永久" and TEXT[at171:at171 + 2] == "永久"
    assert h1.get("negated_suspected") is True
    assert not h2.get("negated_suspected"), "否定语境标记配错位置 = audit=257 的数据矛盾"
