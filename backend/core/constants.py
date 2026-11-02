"""常量唯一来源：分数档位、8 轴枚举、状态枚举、免责声明。

业务文件禁止出现裸数字/裸字符串；需要新增枚举一律加在这里。
枚举同时被 ORM（Enum 列）与 Pydantic（校验）复用，保证两侧同源。
"""

from enum import Enum

# ---------------------------------------------------------------- 分数档位
SCORE_COMPLIANT = 2
SCORE_MINOR = 1
SCORE_VIOLATION = 0
SCORE_INCOMPLETE = -1
VALID_SCORES: tuple[int, ...] = (
    SCORE_COMPLIANT,
    SCORE_MINOR,
    SCORE_VIOLATION,
    SCORE_INCOMPLETE,
)
SCORE_LABELS: dict[int, str] = {
    SCORE_COMPLIANT: "合规",
    SCORE_MINOR: "轻微风险",
    SCORE_VIOLATION: "违规",
    SCORE_INCOMPLETE: "判定未完成（待人工复核）",
}

# ---------------------------------------------------------------- 规则等级
class RuleLevel(str, Enum):
    """规则等级：hard 一票否决，soft 需要累计。"""

    HARD = "hard"
    SOFT = "soft"


# ---------------------------------------------------------------- 规则轴
class RuleAxis(str, Enum):
    """8 条语义轴（db_schema.md §3），是起点不是终点。"""

    ABSOLUTE_TERMS = "absolute_terms"
    EFFICACY_CLAIM = "efficacy_claim"
    SAFETY_GUARANTEE = "safety_guarantee"
    DISEASE_TREATMENT = "disease_treatment"
    FALSE_QUANTIFY = "false_quantify"
    BEFORE_AFTER = "before_after"
    INDUCEMENT = "inducement"
    FALSE_AUTHORITY = "false_authority"


AXIS_LABELS: dict[str, str] = {
    RuleAxis.ABSOLUTE_TERMS.value: "绝对化用语",
    RuleAxis.EFFICACY_CLAIM.value: "功效断言/保证",
    RuleAxis.SAFETY_GUARANTEE.value: "安全性保证",
    RuleAxis.DISEASE_TREATMENT.value: "疾病治疗功能暗示",
    RuleAxis.FALSE_QUANTIFY.value: "无法验证的量化承诺",
    RuleAxis.BEFORE_AFTER.value: "术前术后对比",
    RuleAxis.INDUCEMENT.value: "焦虑式诱导",
    RuleAxis.FALSE_AUTHORITY.value: "虚构权威背书",
}

# 各轴默认等级（db_schema.md §3 表），建规则时若未指定 level 用它兜底
AXIS_DEFAULT_LEVEL: dict[str, str] = {
    RuleAxis.ABSOLUTE_TERMS.value: RuleLevel.HARD.value,
    RuleAxis.EFFICACY_CLAIM.value: RuleLevel.HARD.value,
    RuleAxis.SAFETY_GUARANTEE.value: RuleLevel.HARD.value,
    RuleAxis.DISEASE_TREATMENT.value: RuleLevel.HARD.value,
    RuleAxis.FALSE_QUANTIFY.value: RuleLevel.HARD.value,
    RuleAxis.BEFORE_AFTER.value: RuleLevel.SOFT.value,
    RuleAxis.INDUCEMENT.value: RuleLevel.SOFT.value,
    RuleAxis.FALSE_AUTHORITY.value: RuleLevel.SOFT.value,
}

# ---------------------------------------------------------------- 其它枚举
class UserRole(str, Enum):
    """账号角色；D1 只做区分，不做细粒度授权。"""

    ADMIN = "admin"
    OPERATOR = "operator"


class ScriptStatus(str, Enum):
    """话术状态流转：pending -> audited -> archived。"""

    PENDING = "pending"
    AUDITED = "audited"
    ARCHIVED = "archived"


DEFAULT_INDUSTRY = "medical_beauty"
DEFAULT_PLAN = "free"
DEFAULT_RULE_VERSION = 1

# ---------------------------------------------------------------- 分页
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ---------------------------------------------------------------- 文案
DISCLAIMER_TEXT = (
    "本系统输出为合规风险辅助提示，不构成法律意见，"
    "也不能替代《医疗广告审查证明》的行政前置审查。"
)
