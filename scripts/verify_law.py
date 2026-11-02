"""只读检查法规条号连续性；不修改或补写任何条文。"""
import argparse
import json
import re
from pathlib import Path

ARTICLE_PATTERN = re.compile(r"^第([一二三四五六七八九十百]+)条", re.MULTILINE)
GUIDE_PATTERN = re.compile(r"^([一二三四五六七八九十百]+)、", re.MULTILINE)
DIGITS = dict(zip("一二三四五六七八九", range(1, 10)))
UNITS = {"十": 10, "百": 100}
LAW_DIR = Path(__file__).resolve().parents[1] / "data" / "law"


def chinese_number(value: str) -> int:
    """将百以内中文条号转为整数；未知字符抛出 KeyError。"""
    total, digit = 0, 0
    for char in value:
        if char in UNITS:
            total += (digit or 1) * UNITS[char]
            digit = 0
        else:
            digit = DIGITS[char]
    return total + digit


def body_text(text: str) -> str:
    """先截到首个说明区标题，不改变正文中的任何文字。"""
    endings = ("## 入库建议", "## 核验建议", "## ✅ 完整性说明",
               "## ⚠️ 完整性声明", "## 变更记录")
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(endings):
            return "".join(lines[:index])
    return text


def inspect_text(text: str) -> dict:
    """截正文后选择出现次数较多的编号风格，再检查连续性。"""
    body = body_text(text)
    legal, guide = ARTICLE_PATTERN.findall(body), GUIDE_PATTERN.findall(body)
    numbers = legal if len(legal) >= len(guide) else guide
    articles = sorted({chinese_number(n) for n in numbers})
    maximum = max(articles, default=0)
    missing = sorted(set(range(1, maximum + 1)) - set(articles))
    return {"articles": articles, "maximum": maximum, "missing": missing,
            "continuous": bool(articles) and not missing}


def main(argv: list[str] | None = None) -> int:
    """扫描法规文件；缺号返回 1，未识别正文或基准不符始终返回 1。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-gap", action="store_true", help="忽略已识别正文的缺号")
    args = parser.parse_args(argv)
    files = sorted(p for p in LAW_DIR.glob("*.md") if p.name != "README.md")
    failed = not files
    for path in files:
        text = path.read_text(encoding="utf-8")
        result = inspect_text(text)
        print(path.name)
        print("  已找到条号列表: " + json.dumps(result["articles"]))
        print(f"  最大条号: {result['maximum']}")
        print("  缺号: " + json.dumps(result["missing"]))
        print(f"  是否连续: {'是' if result['continuous'] else '否'}")
        if not result["articles"]:
            print("  未识别编号风格")
            failed = True
        elif path.name == "01_广告法.md" and result["maximum"] != 74:
            print("  基准错误: 2021 版广告法应为 74 条")
            failed = True
        elif result["missing"] and not args.allow_gap:
            failed = True
    print(f"扫描法规文件: {len(files)}；结果: {'失败' if failed else '通过'}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
