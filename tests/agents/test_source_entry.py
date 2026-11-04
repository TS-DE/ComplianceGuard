"""A1 第二个入口（按素材预审 source_id）的接线测试。

本文件证明的是**新接的那一段**：取料、归属校验、上限截断、单条故障标"未完成"、不落库。
刻意替换掉 auditor.review —— A1 内部的判定/引文/打分已有 tests/agents/test_compliance.py 等
专门覆盖；若这里连模型一起跑，出错时说不清是解析错、归属错还是判定错。
"""

from __future__ import annotations

import pytest

from backend.core.errors import BusinessValidationError
from backend.tools import audit_tool, ingest_tool


class _Repo:
    """最小仓储替身：预审路径只用到 client() 存在性校验。"""

    def client(self, client_id):
        return {"id": client_id}

    def load_rules(self, axis=None):
        return []

    def script(self, script_id):
        return None

    def audit(self, audit_id):
        return None


class _Auditor:
    """可编程的 A1 替身：按文本决定给结论还是抛故障，故障用来验"未完成≠合规"。"""

    def __init__(self, fail_on: str | None = None) -> None:
        self.seen: list[str] = []
        self.fail_on = fail_on

    def review(self, text, client_id=None):
        self.seen.append(text)
        if self.fail_on is not None and self.fail_on in text:
            raise RuntimeError("模型超时")
        hit = text.startswith("保证")
        return {"score": 0 if hit else 2, "incomplete": False,
                "hits": ([{"axis": "efficacy_claim", "quote": text[:4],
                           "law_article": "广告法第16条(一)", "reason": "保证性承诺"}]
                         if hit else [])}


def _tool(monkeypatch, auditor: _Auditor, items: list[dict],
          owner: dict | None = None, warnings: list[str] | None = None) -> audit_tool.AuditTool:
    tool = audit_tool.AuditTool(_Repo(), model=object(), search_law=lambda *a, **k: [])
    tool.auditor = auditor
    monkeypatch.setattr(ingest_tool, "source_owner",
                        lambda source_id: owner or {"client_id": 7, "filename": "双11海报.png",
                                                    "kind": "image", "engine": "rapidocr"})
    monkeypatch.setattr(ingest_tool, "parse_stored",
                        lambda source_id, mode="blank": {"items_detail": items,
                                                         "warnings": warnings or []})
    return tool


def test_review_source_reads_items_and_declares_not_persisted(monkeypatch) -> None:
    """预审必须带溯源返回，并明说库里没有记录（不是"已归档"）。"""
    auditor = _Auditor()
    tool = _tool(monkeypatch, auditor, [
        {"text": "保证做完能白三个色度", "ref": "OCR块1", "confidence": 0.93},
        {"text": "效果因人而异请遵医嘱", "ref": "OCR块2", "confidence": 0.88}])

    result = tool.review_source(1)
    assert result["persisted"] is False and result["count"] == 2
    assert result["filename"] == "双11海报.png" and result["kind"] == "image"
    assert [row["ref"] for row in result["results"]] == ["OCR块1", "OCR块2"]
    assert [row["score"] for row in result["results"]] == [0, 2]
    assert "不构成法律意见" in result["disclaimer"], "面向终端用户的输出必须带免责声明"
    assert auditor.seen == ["保证做完能白三个色度", "效果因人而异请遵医嘱"]


def test_model_failure_marks_incomplete_not_compliant(monkeypatch) -> None:
    """铁律 5：判定未完成 ≠ 通过。单条模型故障只能标 -1/incomplete，不许算合规。"""
    tool = _tool(monkeypatch, _Auditor(fail_on="全城最低"), [
        {"text": "保证做完能白三个色度", "ref": "OCR块1", "confidence": 0.9},
        {"text": "全城最低价术后零风险", "ref": "OCR块2", "confidence": 0.9}])

    results = tool.review_source(1)["results"]
    assert results[0]["score"] == 0
    assert results[1]["score"] == -1 and results[1]["incomplete"] is True
    assert "需人工复核" in results[1]["error"]


def test_truncation_is_stated_not_hidden(monkeypatch) -> None:
    """超过上限只审前 20 条，但必须显式说"截断了"，否则看起来像整份都审完。"""
    items = [{"text": f"保证做完第{i}项效果", "ref": f"第{i}页", "confidence": None}
             for i in range(1, 26)]
    result = _tool(monkeypatch, _Auditor(), items).review_source(1, limit=20)
    assert result["count"] == 20 and result["total_items"] == 25
    assert result["truncated"] is True


def test_other_clients_material_is_rejected(monkeypatch) -> None:
    """归属校验按库里的 sources.client_id，不按调用方声明的 client_id。"""
    tool = _tool(monkeypatch, _Auditor(), [{"text": "保证效果", "ref": "第1页",
                                           "confidence": None}])
    with pytest.raises(BusinessValidationError) as exc:
        tool.review_source(1, client_id=999)
    assert "不属于" in str(exc.value)


def test_empty_pieces_are_refused_instead_of_fake_success(monkeypatch) -> None:
    """切不出条目就是失败，不能返回 count=0 让页面显示"全部合规"。"""
    with pytest.raises(BusinessValidationError):
        _tool(monkeypatch, _Auditor(), []).review_source(1)


def test_parse_warnings_reach_the_caller(monkeypatch) -> None:
    """解析层的低置信度警告必须原样带到预审结果，不然 OCR 风险就在链路里被抹平了。"""
    result = _tool(monkeypatch, _Auditor(),
                   [{"text": "保证做完能白三个色度", "ref": "OCR块1", "confidence": 0.4}],
                   warnings=["识别置信度仅 40%，很可能有误读，请对照原始素材人工核对后再采信结论"]
                   ).review_source(1)
    assert result["warnings"] and "人工核对" in result["warnings"][0]
