"""Scope exclusions run before rule evaluation; not per-rule exemptions.

Copied verbatim from data/seeds/rules.json, including traceable sources.
These records are code constants, never a database table.
"""

SCOPE_EXEMPTIONS = [
    {
        "id": "scope_01",
        "text": "医疗机构以医疗科研为目的，发布的招募受试者、临床研究患者等信息，不构成广告。",
        "source": "医疗广告认定指南 第三条",
    },
    {
        "id": "scope_02",
        "text": "医疗机构对患者进行分诊或者就医引导，以及在开展互联网诊疗过程中线上解答患者咨询、指导患者接受诊疗等行为，不构成广告。",
        "source": "医疗广告认定指南 第四条",
    },
    {
        "id": "scope_03",
        "text": "医疗机构在本机构服务场所或自有互联网媒介公开发布机构概况、重点学科、医务人员信息、服务项目、诊疗流程、医保价格收费等信息，不存在该指南第六条规定情形的，不构成广告。",
        "source": "医疗广告认定指南 第五条",
    },
    {
        "id": "scope_04",
        "text": "医疗机构及其医务人员按照医疗卫生健康科普有关要求开展科普宣传，不存在该指南第八条规定情形的，不构成广告。",
        "source": "医疗广告认定指南 第七条",
    },
]

# 引用命名规范与范围常量同族，保持 core 不超过三个功能文件。
import logging
import re

ALIASES = {
    '医美指南': '医疗美容广告执法指南',
    '绝对化用语指南': '广告绝对化用语执法指南',
    '认定指南': '医疗广告认定指南',
    '监管工作指南': '医疗广告监管工作指南',
}
_NUMBERS = dict(zip('零一二三四五六七八九', range(10)))


def _article_number(value):
    """解析中文十百以内条号；非法字符由调用方记录，不猜测。"""
    if value.isdigit():
        return int(value)
    total = digit = 0
    for char in value:
        if char in _NUMBERS:
            digit = _NUMBERS[char]
        elif char in '十百':
            total += (digit or 1) * {'十': 10, '百': 100}[char]
            digit = 0
        else:
            raise ValueError('invalid article number')
    return total + digit


def to_refs(text: str) -> set[str]:
    """引用文本转条级 canonical 集合；省略文档沿用同串上一条，坏片段告警。"""
    refs, previous = set(), ''
    for part in re.split(r'[、，,;；]', text):
        part = re.sub(r'\s+', '', part)
        match = re.fullmatch(r'(.*?)第([0-9零一二三四五六七八九十百]+)条((?:[（(][^）)]*[）)])*)', part)
        if match:
            doc, number, suffix = match.groups()
            doc = ALIASES.get(doc, doc) if doc else previous
            if doc:
                base = f'{doc}.{_article_number(number)}'
                items = re.findall(r'[（(]([0-9零一二三四五六七八九十百]+)[）)]', suffix)
                refs.update({base + '.' + str(_article_number(item)) for item in items} if items else {base})
                previous = doc
                continue
        logging.getLogger(__name__).warning('law_ref_unparsed: %s', part)
    return refs


def missing_docs(refs: set[str], known: set[str]) -> set[str]:
    """输入 canonical 引用和索引文档名；返回缺失文档，不访问基础设施。"""
    return {ref.split('.', 1)[0] for ref in refs} - known

# ── 模型单价兜底表（元/百万tokens）─────────────────────────────
# 取值优先级：.env 的 JUDGE_INPUT_PRICE_PER_M / JUDGE_OUTPUT_PRICE_PER_M
# 高于本表；两者都缺时 cost = None（不是 0）。
# 价格会变动，as_of 为抓取日期；本表仅用于估算，非账单金额。
MODEL_PRICES = {
    # as_of: 2026-11-03，阿里云百炼控制台 qwen3.8-flash 标价
    "qwen3.8-flash": {"in": 0.8, "out": 2.7},
}


from decimal import Decimal, InvalidOperation


def compute_cost(prompt_tokens, completion_tokens, price_in, price_out):
    """按百万 token 单价计费；缺价为 None，非法数值抛 ValueError。"""
    try:
        prices = [None if p is None or p == '' else Decimal(str(p)) for p in (price_in, price_out)]
        if any(p is not None and (not p.is_finite() or p < 0) for p in prices):
            raise ValueError('模型报价必须是有限非负数')
        if any(type(n) is not int or n < 0 for n in (prompt_tokens, completion_tokens)):
            raise ValueError('token 用量必须是非负整数')
        if None in prices:
            return None
        return ((prompt_tokens * prices[0] + completion_tokens * prices[1]) / Decimal('1000000')).quantize(Decimal('0.000001'))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('模型报价非法') from exc


def add_cost(left, right):
    """任一费用未知时累计费用也未知，不用零掩盖未知。"""
    return None if left is None or right is None else Decimal(str(left)) + Decimal(str(right))



def match_refs(declared, cited):
    """精确项号优先；只有证据确无项号才显式降级到条级。"""
    if declared & cited:
        return 'matched'
    for rule in declared:
        for hit in cited:
            a, b = rule.split('.'), hit.split('.')
            if a[:2] == b[:2]:
                if len(a) == 2:
                    return 'matched'
                if len(b) == 2:
                    return 'matched_at_article_level'
    if any(a.split('.')[:2] == b.split('.')[:2] for a in declared for b in cited):
        return 'item_mismatch'
    return 'cross_axis_rejected'


def chunk_refs(chunk):
    """项号仅继承可信chunk元数据；模型输出不得提供或覆盖item_no。"""
    code = chunk['code']
    item = chunk.get('item_no')
    suffix = re.search(r'[（(]([0-9零一二三四五六七八九十百]+)[）)]', str(item or ''))
    return {ref + '.' + str(_article_number(suffix.group(1))) for ref in to_refs(code)} if suffix else to_refs(code)



def bind_chunk(hit, refs):
    """只按模型引用的稳定ID或code选择当前检索证据；不接受模型项号。"""
    cited = hit.get('chunk_id') or hit.get('law_article')
    chunks = [r for r in refs if r.get('chunk_id') == cited or r['code'] == cited]
    if len(chunks) != 1:
        return None
    chunk = chunks[0]
    hit.update(law_article=chunk['code'], code=chunk['code'], item_no=chunk.get('item_no'),
               chunk_id=chunk.get('chunk_id'), ref=next(iter(chunk_refs(chunk))))
    return chunk


# ---------------------------------------------------------------------------
# 分级判定用的两组客观特征词（写在代码里，保证可复算、可解释）
#
# 背景：模型把「皮肤愈合后，应更显光滑」「可能需要大约三个月时间才能恢复正常肤色」
# 这类**预后/恢复周期的常规告知**判成了「功效断言」。根因是判定只有"命中/不命中"，
# 没有区分"向顾客打包票"与"描述一般规律"。
#
# 处理不是放行，而是**降级**：命中仍保留（商家仍会被提示），严重度从 hard 降为 soft，
# 分数由 0 变 1，界面显示"疑似违规 · 建议复核"。
# 这样既不误杀正常宣传，也不会把该提示的风险吞掉。
# ---------------------------------------------------------------------------

# 承诺词：向顾客承诺确定结果，出现即保持硬命中
COMMITMENT_WORDS = (
    "保证", "一定能", "一定能达到", "必然", "彻底", "百分百", "100%", "百分之百",
    "绝对", "永不", "不反弹", "无效退款", "包见效", "一次见效", "根治", "永久",
    "绝不", "确保", "一定能", "必能",
)

# 模糊限定词：说明是预估 / 一般规律 / 存在个体差异
HEDGE_WORDS = (
    "可能", "大约", "大概", "通常", "一般", "因人而异", "个体差异", "仅供参考",
    "预计", "视情况", "通常情况下", "一般情况下", "多数人", "部分人", "应",
)
