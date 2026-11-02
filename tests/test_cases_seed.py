"""罚单案例文件结构校验（锚点集只校验结构，不校验"对错"）。"""

from scripts.seed_cases import CASES_DIR, load_cases


def test_case_files_valid_and_unique() -> None:
    cases, errors = load_cases(CASES_DIR)
    assert errors == []
    assert len(cases) >= 2
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        assert case.law_articles
        assert case.penalty_amount > 0
