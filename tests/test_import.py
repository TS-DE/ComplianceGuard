"""商家文案批量导入：切分规则与导入接口。

这是回应「商家给的不是一条条数据，而是一页页文档」的核心能力。
关键取舍都写进用例：切分模式、剥序号、去重、过短过滤、不支持格式明确报错。
"""

import io
import json

from fastapi.testclient import TestClient

from backend.tools.extract_tool import MAX_BYTES, extract_text, split_scripts

API = "/api/v1"


def test_split_blank_mode_splits_by_blank_line() -> None:
    """空行模式：一段话术=一个自然段，段内换行压平成一行。"""
    text = "第一段是完整话术，内容够长。\n仍然属于第一段。\n\n第二段是另一条话术，也够长。"
    pieces = split_scripts(text, "blank")
    assert len(pieces) == 2
    assert pieces[0] == "第一段是完整话术，内容够长。 仍然属于第一段。"
    assert pieces[1] == "第二段是另一条话术，也够长。"


def test_split_line_mode_splits_by_single_newline() -> None:
    """行模式：一行一条，这是清单式素材的常见形态。"""
    text = "保证做完效果翻倍\n效果因人而异，请遵医嘱\n第三行也是一条话术"
    assert len(split_scripts(text, "line")) == 3


def test_split_strips_leading_numbering() -> None:
    """序号是文档结构不是话术内容，必须剥掉，否则引文会带上 "1." 噪声。"""
    text = "1. 保证做完双眼皮能白两个度\n2、我们是全城最好的机构\n（3）术后零风险\n一、不能保证效果\n- 今天预约立减五百元"
    pieces = split_scripts(text, "line")
    assert pieces == [
        "保证做完双眼皮能白两个度",
        "我们是全城最好的机构",
        "术后零风险",
        "不能保证效果",
        "今天预约立减五百元",
    ]


def test_split_dedupes_and_drops_short_pieces() -> None:
    """重复内容只留一条；2 字噪声（如"备注"）直接丢，但 5 字的合法短话术要保留。"""
    text = "这是一条足够长的话术内容\n这是一条足够长的话术内容\n备注\n术后零风险"
    pieces = split_scripts(text, "line")
    assert pieces == ["这是一条足够长的话术内容", "术后零风险"]


def test_split_rejects_unknown_mode() -> None:
    """模式写错要立刻报错，而不是悄悄按默认切（否则会切错还看不出来）。"""
    try:
        split_scripts("任意内容足够长的话术", "paragraph")
    except ValueError as exc:
        assert "blank" in str(exc)
    else:  # pragma: no cover - 走到这里说明没报错
        raise AssertionError("非法 mode 应当抛 ValueError")


def test_extract_text_handles_utf8_and_gb18030() -> None:
    """Windows 记事本常见 GB18030，必须能读，否则商家上传就报错。"""
    assert extract_text("a.txt", "中文内容".encode("utf-8")) == "中文内容"
    assert extract_text("b.txt", "中文内容".encode("gb18030")) == "中文内容"


def test_extract_text_rejects_unsupported_and_oversized() -> None:
    """不支持的类型/超大文件明确拒绝，不做模糊处理。"""
    for name in ("a.png", "a.exe", "a"):
        try:
            extract_text(name, b"x")
        except ValueError as exc:
            assert "不支持" in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"{name} 应当被拒绝")
    try:
        extract_text("big.txt", b"x" * (MAX_BYTES + 1))
    except ValueError as exc:
        assert "MB" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("超大文件应当被拒绝")


def test_extract_text_from_docx() -> None:
    """docx 抽取段落与表格文字。"""
    import docx

    document = docx.Document()
    document.add_paragraph("第一段医美话术内容")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "表格里的"
    table.rows[0].cells[1].text = "话术内容"
    buffer = io.BytesIO()
    document.save(buffer)

    text = extract_text("a.docx", buffer.getvalue())
    assert "第一段医美话术内容" in text
    assert "表格里的" in text


def test_import_api_preview_then_commit(client: TestClient, auth_headers: dict, db) -> None:
    """两段式：先预览不落库，再勾选入库。"""
    from backend.db.models import Client

    account = Client(name="导入测试机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()

    payload = {"client_id": str(account.id), "commit": "false", "mode": "line",
               "text": "保证做完效果翻倍\n效果因人而异，请遵医嘱"}
    preview = client.post(f"{API}/scripts/import", data=payload, headers=auth_headers)
    assert preview.status_code == 200, preview.text
    body = preview.json()["data"]
    assert body["count"] == 2 and body["created"] == 0 and body["script_ids"] == []

    # 只提交勾选的一条：切分不可能百分百正确，必须允许人工剔除。
    commit = client.post(f"{API}/scripts/import", headers=auth_headers, data={
        "client_id": str(account.id), "commit": "true", "mode": "line",
        "text": "保证做完效果翻倍\n效果因人而异，请遵医嘱",
        "items": json.dumps(["保证做完效果翻倍"], ensure_ascii=False),
    })
    assert commit.status_code == 200, commit.text
    result = commit.json()["data"]
    assert result["created"] == 1 and len(result["script_ids"]) == 1

    listed = client.get(f"{API}/scripts", params={"client_id": account.id}, headers=auth_headers)
    assert listed.json()["total"] == 1


def test_import_api_rejects_unsupported_file(client: TestClient, auth_headers: dict, db) -> None:
    """不支持的类型返回 422 且说明支持哪些格式。"""
    from backend.db.models import Client

    account = Client(name="导入测试机构2", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()

    resp = client.post(
        f"{API}/scripts/import",
        data={"client_id": str(account.id), "commit": "false"},
        files={"file": ("a.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "不支持" in resp.json()["msg"]


def test_redteam_options_exposes_what_will_be_tested(client: TestClient, auth_headers: dict, db) -> None:
    """压测页必须能说明"这一轮测什么"：模型、各轴规则版本、检测手段与样本计划。

    没有这份元信息，界面上只有"16 条"，管理员既不知道测的是哪些轴，
    也无法把漏杀结果和某次规则改动对应起来。
    """
    from backend.db.models import Rule

    db.add(Rule(axis="efficacy_claim", law_article="广告法第16条(一)",
                pattern="对诊疗效果作保证性承诺", level="hard", detector="llm_judge",
                example_bad=None, version=3, enabled=True))
    db.commit()

    resp = client.get(f"{API}/redteam/options", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["model"], "必须暴露本轮使用的模型名"
    axes = {item["axis"]: item for item in data["axes"]}
    assert set(axes) == {"efficacy_claim", "safety_guarantee", "absolute_terms", "inducement"}
    assert axes["efficacy_claim"]["version"] == 3
    assert axes["efficacy_claim"]["detector"] == "llm_judge"
    assert data["plan"]["per_axis_samples"] == 4
    assert "合规对照" in data["plan"]["description"]
