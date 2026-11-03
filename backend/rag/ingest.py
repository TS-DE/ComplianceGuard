"""只读解析法规结构及官方罚单，不改写归档原文、不触发网络调用。"""
import json
import re
from functools import lru_cache
from pathlib import Path

from scripts.verify_law import ARTICLE_PATTERN, GUIDE_PATTERN, body_text, chinese_number

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAW_DIR = DATA_DIR / "law"
CASE_DIR = DATA_DIR / "cases"
HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
NUMBER = r"[一二三四五六七八九十百]+|\d+"
DOMAIN_TERMS = (
    ('medical', ('医疗', '药品', '医疗器械', '保健食品', '医美', '医疗广告', '诊疗')),
    ('agriculture', ('农药', '兽药', '饲料', '种子', '种畜禽', '水产苗种')),
    ('tobacco_alcohol', ('烟草', '酒类')),
    ('realestate_edu', ('房地产', '教育培训', '招商', '投资回报')),
    ('minor_media', ('未成年人', '母乳', '中小学校', '幼儿园')),
)


def classify_domain(text: str) -> str:
    """按固定优先级判定完整条款行业；子块继承，避免列表项丢失行业上下文。"""
    return next((name for name, terms in DOMAIN_TERMS if any(t in text for t in terms)), 'general')


def _footer_labels(text: str) -> dict[int, str]:
    """读取归档尾部标签表；未标注的条文交给可解释的性质判定。"""
    labels = {}
    footer = text[len(body_text(text)):]
    for line in footer.splitlines():
        cells = line.split("|")
        if len(cells) < 4:
            continue
        label = re.search(r"\b(decision|procedure)\b", cells[2])
        if not label:
            continue
        numbers = re.findall(NUMBER, cells[1])
        values = [int(n) if n.isdigit() else chinese_number(n) for n in numbers]
        if len(values) == 2:
            values = range(values[0], values[1] + 1)
        for value in values:
            labels[value] = label.group(1)
    return labels


def _relevance(text: str) -> tuple[str, str]:
    """无标签时按程序/罚则及内容义务判定，返回类别和可审计原因。"""
    if re.search(r"罚款|没收|吊销|责令|施行|制定本法|制定本指南|监督管理工作|档案|工作日|书面合同|广告业务|收费标准|主管部门|审查申请|审查批准|合法经营资格", text):
        return "procedure", "fallback:程序、监督、罚则或施行条款"
    if re.search(r"不得|禁止|应当|是指|适用本法|构成|不视为|真实|公平竞争", text):
        return "decision", "fallback:定义、范围或广告内容义务"
    return "procedure", "fallback:未发现直接内容判定义务"


def _articles(text: str):
    """正文按主要编号风格切条；章标题及归档说明不进入条文。"""
    body = HTML_TAG.sub("", body_text(text))
    pattern = ARTICLE_PATTERN if len(ARTICLE_PATTERN.findall(body)) >= len(GUIDE_PATTERN.findall(body)) else GUIDE_PATTERN
    matches = list(pattern.finditer(body))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        article = re.split(r"(?m)^#{1,6} |^---\s*$", body[match.start():end])[0].strip()
        yield chinese_number(match.group(1)), article


def _children(parent: str, split_paragraphs: bool = False):
    """显式项逐项切分；长条文和归档指定的多款条文逐款切分。"""
    item_pattern = re.compile(rf"^[（(]({NUMBER})[）)]", re.MULTILINE)
    item_matches = list(item_pattern.finditer(parent))
    if not item_matches:
        if not split_paragraphs:
            yield parent, ""
            return
        for paragraph in re.split(r"\n\s*\n", parent):
            if paragraph.strip():
                yield paragraph.strip(), ""
        return
    for index, match in enumerate(item_matches):
        end = item_matches[index + 1].start() if index + 1 < len(item_matches) else len(parent)
        paragraphs = re.split(r"\n\s*\n", parent[match.start():end].strip())
        yield paragraphs[0], match.group(1)
        for paragraph in paragraphs[1:]:
            if paragraph.strip():
                yield paragraph.strip(), ""


def _bounded(text: str, budget: int):
    """依次优先款界、句界、分号及逗号；无界超长原文才硬切且不丢字。"""
    if budget <= 0:
        raise ValueError("条号前缀超过分块长度限制")
    while len(text) > budget:
        window = text[:budget]
        end = 0
        for separator in ("\n", "。", "；", "，"):
            position = window.rfind(separator)
            if position >= 0:
                end = position + 1
                break
        end = end or budget
        yield text[:end]
        text = text[end:]
    if text:
        yield text


def load_laws() -> tuple[list[dict], int]:
    """返回判定条文和跳过的程序性条文数；文件读写错误原样抛出。"""
    records, skipped = [], 0
    for path in sorted(LAW_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        labels = _footer_labels(text)
        title = re.sub(r"^\d+_", "", path.stem)
        doc_type = "guideline" if "指南" in title else "measure" if "办法" in title else "law"
        for number, parent in _articles(text):
            relevance, reason = _relevance(parent)
            if number in labels:
                relevance, reason = labels[number], "footer:入库标签表"
            if relevance == "procedure":
                skipped += 1
                continue
            code = f"{title}第{number}条"
            metadata = dict(code=code, doc_type=doc_type, relevance=relevance,
                            source=path.name, article_no=number, parent_text=parent,
                            relevance_reason=reason, domain=classify_domain(parent))
            split = (len(parent) + len(code) + 1 > 400
                     or (title, number) in {("医疗广告认定指南", 5), ("医疗广告监管工作指南", 11)})
            for index, (child, item) in enumerate(_children(parent, split), start=1):
                child_meta = metadata.copy()
                if item:
                    numeral = re.match(rf"第({NUMBER})条|({NUMBER})、", parent)
                    assert numeral is not None
                    article_label = next(v for v in numeral.groups() if v)
                    child_meta["item_no"] = f"第{article_label}条({item})"
                for part, piece in enumerate(_bounded(child, 400 - len(code) - 1), start=1):
                    records.append(dict(id=f"{path.stem}:{number}:{index}:{part}",
                                        text=f"{code}\n{piece}", metadata=child_meta.copy()))
    return records, skipped


def load_cases() -> list[dict]:
    """每份罚单返回一个完整块；缺失必需字段或无效 JSON 原样报错。"""
    records = []
    for path in sorted(CASE_DIR.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        text = (f"{case['title']}\n违规原话：{case['violation_quote']}\n"
                f"官方定性：{case['official_ruling']}\n罚款金额：{case['penalty_amount']}元")
        metadata = {key: value for key, value in case.items()
                    if value is not None and type(value) in (str, int, float, bool)}
        metadata.update(code=case["case_id"], doc_type="case", relevance="decision",
                        source=case.get("source") or case["source_url"], parent_text=text, article_no=0,
                        source_file=path.name, domain=classify_domain(text),
                        law_articles="；".join(case.get("law_articles", [])))
        records.append(dict(id=case["case_id"], text=text, metadata=metadata))
    return records


@lru_cache(maxsize=1)
def law_catalog() -> dict[str, dict]:
    """返回「法规全称 -> {title, source, articles}」，每条含该条完整原文。

    与 `load_laws()` 的区别：这里**不跳过 procedure 条款**。
    原因：前端要的是「完整法规 + 定位到该条」，若沿用入库口径，广告法只会剩 41/74 条、
    医美指南只剩 4/10 条，用户看到的就不是完整法规了。入库求精度，追溯求完整。
    """
    catalog: dict[str, dict] = {}
    for path in sorted(LAW_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        title = re.sub(r"^\d+_", "", path.stem)
        articles = [dict(code=f"{title}第{number}条", article_no=number, text=parent)
                    for number, parent in _articles(path.read_text(encoding="utf-8"))]
        articles.sort(key=lambda item: item["article_no"])
        catalog[title] = dict(title=title, source=path.name, articles=articles)
    return catalog


def find_law_article(code: str) -> dict | None:
    """按条文 code 定位，返回该条原文与所属法规的全部条文；未收录返回 None。

    返回 articles 是为了让前端能同屏渲染上下文并滚动高亮目标条，
    避免只给一根孤立的条文而失去「在整部法规中的位置」这一追溯价值。
    """
    for doc in law_catalog().values():
        for article in doc["articles"]:
            if article["code"] == code:
                return dict(doc=doc["title"], source=doc["source"], code=article["code"],
                            article_no=article["article_no"], text=article["text"],
                            articles=doc["articles"])
    return None
