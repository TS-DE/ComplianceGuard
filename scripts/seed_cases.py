"""灌入罚单案例（data/cases/*.json）。

D1 范围：读取 + 结构校验 + 去重报告，作为 D2 建 Chroma 索引的输入前置检查。
**尚未写 Chroma**（D2 的 scripts/build_index.py 负责），因此本脚本可重复执行、
不产生任何副作用；校验失败则非零退出。

用法：
    python -m scripts.seed_cases            # 校验并汇总
    python -m scripts.seed_cases --strict   # 有任何警告也非零退出
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from backend.schemas.business import CaseRecord

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("seed_cases")

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "data" / "cases"
# 锚点集目标条数（db_schema.md §2.2）
TARGET_CASE_COUNT = 30


def emit(line: str = "") -> None:
    """面向人的报告输出；仅纯文本，不含 emoji（Windows GBK 安全）。"""
    sys.stdout.write(line + "\n")


def load_cases(directory: Path) -> tuple[list[CaseRecord], list[str]]:
    """读取目录下所有 json 并校验。

    返回:
        (有效案例列表, 错误信息列表)
    """
    cases: list[CaseRecord] = []
    errors: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # 新归档使用多轴 violation_type；适配旧展示字段，不改罚单原文。
            if 'category' not in raw:
                raw['category'] = ' / '.join(raw.get('violation_type', [])) or raw['official_ruling']
            raw.setdefault('source', raw.get('source_url'))
            cases.append(CaseRecord.model_validate(raw))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{path.name}: {exc}")
    return cases, errors


def main(argv: list[str] | None = None) -> int:
    """入口：校验案例文件并打印汇总。"""
    parser = argparse.ArgumentParser(description="校验罚单案例文件")
    parser.add_argument("--strict", action="store_true", help="条数不足也视为失败")
    args = parser.parse_args(argv)

    if not CASES_DIR.is_dir():
        logger.error("案例目录不存在: %s", CASES_DIR)
        return 1

    cases, errors = load_cases(CASES_DIR)
    seen: dict[str, str] = {}
    for case in cases:
        if case.case_id in seen:
            errors.append(f"case_id 重复: {case.case_id}")
        seen[case.case_id] = case.title

    emit(f"案例目录: {CASES_DIR}")
    emit(f"有效案例: {len(cases)} 条 / 目标 {TARGET_CASE_COUNT} 条")
    for case in cases:
        emit(
            f"  - {case.case_id} | {case.year} | 罚款 {case.penalty_amount} 元 | "
            f"{case.authority} | {case.category}"
        )
    for err in errors:
        logger.error("%s", err)

    if errors:
        return 1
    if args.strict and len(cases) < TARGET_CASE_COUNT:
        logger.error("案例条数不足目标 %d 条", TARGET_CASE_COUNT)
        return 1
    emit("说明：D1 仅做结构校验；入库 Chroma 由 D2 的 scripts/build_index.py 完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
