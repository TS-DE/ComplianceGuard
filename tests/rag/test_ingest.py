"""法规和罚单只读入库的契约与逐字完整性测试。"""
import importlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def ingest_module():
    """缺实现时用断言而不是导入错误报告缺失功能。"""
    assert importlib.util.find_spec("backend.rag.ingest"), "D2 ingestion is missing"
    return importlib.import_module("backend.rag.ingest")


def test_load_laws_returns_decision_records_with_stable_ids():
    ingest = ingest_module()
    records, skipped = ingest.load_laws()
    assert records and skipped > 0
    assert (records, skipped) == ingest.load_laws()
    assert len({row["id"] for row in records}) == len(records)
    assert {row["metadata"]["source"] for row in records} == {
        path.name for path in (ROOT / "data/law").glob("*.md")
        if path.name != "README.md"
    }
    for row in records:
        assert set(row) == {"id", "text", "metadata"}
        meta = row["metadata"]
        assert meta["relevance"] == "decision"
        assert meta["doc_type"] in {"law", "regulation", "guideline", "measure"}
        assert meta["article_no"] > 0
        assert row["text"].startswith(meta["code"] + "\n")
        assert meta["parent_text"]
        assert all(type(v) in (str, int, float, bool) for v in meta.values())
    assert any(row["metadata"]["code"] == "广告法第16条" for row in records)


def test_all_explicit_items_are_independent_and_keep_complete_parent():
    records, _ = ingest_module().load_laws()
    expected = [("04_", 5, 3), ("04_", 6, 6), ("03_", 5, 9),
                ("05_", 6, 5), ("05_", 8, 5), ("02_", 6, 4),
                ("02_", 8, 6), ("02_", 12, 5), ("01_", 16, 5)]
    for prefix, number, count in expected:
        rows = [r for r in records if r["metadata"]["source"].startswith(prefix)
                and r["metadata"]["article_no"] == number]
        items = [r for r in rows if "item_no" in r["metadata"]]
        assert len(items) == count, (prefix, number)
        assert len({r["metadata"]["item_no"] for r in items}) == count
        assert len({r["metadata"]["parent_text"] for r in rows}) == 1
        for row in rows:
            payload = row["text"].split("\n", 1)[1]
            assert payload in row["metadata"]["parent_text"]
    fifth = [r for r in records if r["metadata"]["code"] == "医疗广告认定指南第5条"]
    assert len(fifth) == 3  # 自有媒介、第三方平台与公开要求三款均不丢弃。
    eleventh = [r for r in records if r["metadata"]["code"] == "医疗广告监管工作指南第11条"]
    assert len(eleventh) == 2


def test_long_children_are_bounded_exact_substrings_without_lost_text(tmp_path, monkeypatch):
    ingest = ingest_module()
    first = "第一条　" + "甲" * 250 + "。" + "乙" * 250 + "；" + "丙" * 500 + "。"
    (tmp_path / "99_测试法.md").write_text(
        "<div>" + first + "</div>\n\n## 入库建议\n"
        "| 条号 | relevance |\n| 一 | decision |\n", encoding="utf-8")
    monkeypatch.setattr(ingest, "LAW_DIR", tmp_path)
    records, skipped = ingest.load_laws()
    assert skipped == 0
    assert len(records) > 1
    assert all(len(r["text"]) <= 400 for r in records)
    pieces = [r["text"].split("\n", 1)[1] for r in records]
    assert "".join(pieces) == first
    assert all(r["metadata"]["parent_text"] == first for r in records)
    assert all(piece in first for piece in pieces)
    assert pieces[0].endswith("。")  # 优先句界，而非机械窗口。


def test_cases_are_single_complete_chunks_with_primitive_metadata():
    ingest = ingest_module()
    assert hasattr(ingest, "load_cases"), "case ingestion is missing"
    records = ingest.load_cases()
    paths = sorted((ROOT / "data/cases").glob("*.json"))
    assert len(records) == len(paths)
    assert records == ingest.load_cases()
    assert len({r["id"] for r in records}) == len(records)
    for path, row in zip(paths, records):
        case = json.loads(path.read_text(encoding="utf-8"))
        assert row["id"] == case["case_id"]
        assert case["violation_quote"] in row["text"]
        assert case["official_ruling"] in row["text"]
        assert str(case["penalty_amount"]) in row["text"]
        meta = row["metadata"]
        assert meta["doc_type"] == "case"
        assert meta["relevance"] == "decision"
        assert meta["source"] == case["source"]
        assert meta["parent_text"] == row["text"]
        assert meta["penalty_amount"] == case["penalty_amount"]
        assert all(type(v) in (str, int, float, bool) for v in meta.values())


def test_footer_tables_override_fallback_and_skip_count_is_per_article(tmp_path, monkeypatch):
    ingest = ingest_module()
    text = ("第一条　广告不得使用最佳等用语。\n\n"
            "第二条　广告主应当依法订立书面合同。\n\n"
            "第三条　机关应当在十个工作日完成审查。\n\n"
            "第四条　广告不得贬低同行。\n\n## 入库建议\n"
            "| 条号 | relevance |\n| **第 1 条** | `procedure` |\n"
            "| 第三条 | **decision** ★ |\n")
    (tmp_path / "99_测试法.md").write_text(text, encoding="utf-8")
    monkeypatch.setattr(ingest, "LAW_DIR", tmp_path)
    records, skipped = ingest.load_laws()
    assert skipped == 2
    assert {r["metadata"]["article_no"] for r in records} == {3, 4}
    assert {r["metadata"]["relevance_reason"] for r in records} == {
        "footer:入库标签表", "fallback:定义、范围或广告内容义务"}


def test_corpus_labels_and_exact_original_parents():
    ingest = ingest_module()
    records, skipped = ingest.load_laws()
    total_articles = 0
    for path in (ROOT / "data/law").glob("*.md"):
        if path.name == "README.md":
            continue
        raw = path.read_text(encoding="utf-8")
        total_articles += len(list(ingest._articles(raw)))
        for row in [r for r in records if r["metadata"]["source"] == path.name]:
            meta = row["metadata"]
            assert meta["parent_text"] in re.sub(r"</?[A-Za-z][^>]*>", "", raw)
            assert row["text"].split("\n", 1)[1] in meta["parent_text"]
            assert len(row["text"]) <= 400
            assert "##" not in meta["parent_text"]
            assert "入库建议" not in row["text"]
            if path.name.startswith("01_"):
                assert meta["article_no"] < 69
            if path.name.startswith("04_"):
                assert meta["article_no"] not in {1, 3, 8, 9, 10, 12}
    unique_articles = {(r["metadata"]["source"], r["metadata"]["article_no"]) for r in records}
    assert len(unique_articles) + skipped == total_articles
    assert any(r["metadata"]["code"] == "广告法第68条" for r in records)


def test_short_non_list_articles_stay_whole():
    rows, _ = ingest_module().load_laws()
    fourth = [r for r in rows if r["metadata"]["code"] == "广告法第4条"]
    assert len(fourth) == 1
    assert fourth[0]["text"].split("\n", 1)[1] == fourth[0]["metadata"]["parent_text"]
