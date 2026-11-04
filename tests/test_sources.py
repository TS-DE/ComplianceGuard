"""素材摄取与溯源的端到端回归：上传 → 预览 → 入库 → 回看原始文件 → 越权隔离。

这一组用例证明的是产品主线："商家给的是整份文件，不是一条条话术"。
解析质量在 tests/parse/ 用假引擎测，这里只管**链路与契约**，所以用 docx/txt（无模型、无网络）。

刻意验证的三件事：
1. 预览一行都不写（库和磁盘都不写）；
2. 溯源由服务端算，客户端伪造不了；
3. 商家之间互相看不见对方的素材，也点不开别人的原始文件。
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API = "/api/v1"
PARAGRAPHS = ["保证做完双眼皮能往上走三个色度", "我们是全城最好的机构，效果永久"]


def _docx(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _merchant(client: TestClient, username: str, name: str) -> dict:
    """注册一个商家账号：注册即建机构并绑定，商家端才有归属可写。"""
    client.post(f"{API}/auth/register",
                json={"username": username, "password": "Sources12345",
                      "role": "merchant", "client_name": name})
    login = client.post(f"{API}/auth/login",
                        json={"username": username, "password": "Sources12345"})
    data = login.json()["data"]
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"},
            "client_id": data["user"]["client_id"]}


def _upload(client: TestClient, headers: dict, client_id: int, raw: bytes,
            commit: bool, name: str = "话术.docx") -> dict:
    resp = client.post(f"{API}/scripts/import", headers=headers,
                       data={"client_id": str(client_id), "commit": str(commit).lower()},
                       files={"file": (name, raw, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------- 两段式
def test_preview_writes_nothing_to_db_or_disk(client: TestClient, auth_headers: dict, db) -> None:
    """预览必须一行都不写：写库会污染审计统计，落盘会在磁盘堆垃圾。"""
    from backend.core.config import settings
    from backend.db.models import Client

    account = Client(name="预览机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()
    before = sorted(str(p) for p in Path(settings.upload_path).rglob("*") if p.is_file())

    body = _upload(client, auth_headers, account.id, _docx(PARAGRAPHS), commit=False)
    assert body["count"] == 2 and body["created"] == 0 and body["script_ids"] == []
    assert body["items"] == PARAGRAPHS, "items 仍是字符串数组，上一版前端不必改"
    assert [item["text"] for item in body["items_detail"]] == PARAGRAPHS
    assert [item["ref"] for item in body["items_detail"]] == ["第1段", "第2段"]
    assert body["kind"] == "docx" and body["engine"] == "python-docx"
    assert body["confidence"] is None, "文本层不该有置信度"

    assert client.get(f"{API}/scripts", headers=auth_headers).json()["total"] == 0
    after = sorted(str(p) for p in Path(settings.upload_path).rglob("*") if p.is_file())
    assert after == before, "预览阶段不应该写任何文件"


def test_commit_persists_source_and_provenance(client: TestClient, auth_headers: dict, db) -> None:
    """入库产生一份素材档案 + N 条带位置的话术，且原始文件可回看。"""
    from backend.db.models import Client

    account = Client(name="入库机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()
    raw = _docx(PARAGRAPHS)

    body = _upload(client, auth_headers, account.id, raw, commit=True)
    assert body["created"] == 2 and len(body["script_ids"]) == 2

    listed = client.get(f"{API}/sources", headers=auth_headers).json()
    assert listed["total"] == 1
    source = listed["data"][0]
    assert source["filename"] == "话术.docx" and source["item_count"] == 2
    assert source["kind"] == "docx" and source["engine"] == "python-docx"
    assert source["file_available"] is True
    assert "stored_path" not in source, "内部文件布局不该出现在响应里"

    detail = client.get(f"{API}/sources/{source['id']}", headers=auth_headers).json()["data"]
    assert [row["content"] for row in detail["scripts"]] == PARAGRAPHS
    assert [row["ref"] for row in detail["scripts"]] == ["第1段", "第2段"]

    # 话术列表自己也要带溯源：审查记录页不必为了显示"第1段"再多发一次请求
    scripts = client.get(f"{API}/scripts", params={"client_id": account.id},
                         headers=auth_headers).json()["data"]
    assert {row["source_id"] for row in scripts} == {source["id"]}
    assert sorted(row["source_ref"] for row in scripts) == ["第1段", "第2段"]


def test_original_file_is_served_inline(client: TestClient, auth_headers: dict, db) -> None:
    """原始素材内联返回：核对海报/录音时不能每次都被迫下载。"""
    from backend.db.models import Client

    account = Client(name="回看机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()
    raw = _docx(PARAGRAPHS)
    body = _upload(client, auth_headers, account.id, raw, commit=True)

    resp = client.get(f"{API}/sources/{body['source_id']}/file", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == raw, "回看必须拿到当初上传的那份文件，一个字节都不能差"
    assert "inline" in resp.headers["content-disposition"]


# ---------------------------------------------------------------- 溯源不可伪造
def test_client_cannot_forge_provenance(client: TestClient, auth_headers: dict, db) -> None:
    """勾选回来的条目只认文本：库里的位置必须是服务端重算的，不是前端传来的。"""
    from backend.db.models import Client

    account = Client(name="伪造机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()

    forged = client.post(f"{API}/scripts/import", headers=auth_headers, data={
        "client_id": str(account.id), "commit": "true",
        "items": json.dumps([{"text": PARAGRAPHS[0], "ref": "第99页",
                              "confidence": 0.99}], ensure_ascii=False),
    }, files={"file": ("a.docx", _docx(PARAGRAPHS), "application/octet-stream")})
    assert forged.status_code == 422
    assert "JSON 字符串数组" in forged.json()["msg"]


def test_item_not_in_file_is_rejected(client: TestClient, auth_headers: dict, db) -> None:
    """文件里没有的句子不能入库：宁可拒绝，也不留一条"不知道从哪来"的话术。"""
    from backend.db.models import Client

    account = Client(name="幻觉机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()

    resp = client.post(f"{API}/scripts/import", headers=auth_headers, data={
        "client_id": str(account.id), "commit": "true",
        "items": json.dumps(["这句文件里根本没有，是前端编的"], ensure_ascii=False),
    }, files={"file": ("a.docx", _docx(PARAGRAPHS), "application/octet-stream")})
    assert resp.status_code == 422
    assert "对不上" in resp.json()["msg"]
    assert client.get(f"{API}/scripts", headers=auth_headers).json()["total"] == 0


def test_duplicate_upload_is_pointed_out(client: TestClient, auth_headers: dict, db) -> None:
    """同一份素材重复上传要指出来（按内容指纹，不按文件名）。"""
    from backend.db.models import Client

    account = Client(name="重复机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()
    raw = _docx(PARAGRAPHS)

    first = _upload(client, auth_headers, account.id, raw, commit=True)
    second = _upload(client, auth_headers, account.id, _docx(PARAGRAPHS),
                     commit=True, name="话术-改了三遍-最终版.docx")
    assert second["duplicate_of"] == first["source_id"], "改了文件名也还是同一份素材"


# ---------------------------------------------------------------- 租户隔离
def test_merchants_cannot_see_each_others_materials(client: TestClient) -> None:
    """商家之间素材完全隔离：列表看不到，详情与原始文件按 404 处理。"""
    shop_a = _merchant(client, "shop_src_a", "阿尔法医美")
    shop_b = _merchant(client, "shop_src_b", "贝塔口腔")

    a_body = _upload(client, shop_a["headers"], shop_a["client_id"], _docx(PARAGRAPHS), True)
    b_body = _upload(client, shop_b["headers"], shop_b["client_id"],
                     _docx(["贝塔家自己的违规话术内容"]), True)

    mine = client.get(f"{API}/sources", headers=shop_a["headers"]).json()
    assert mine["total"] == 1 and mine["data"][0]["id"] == a_body["source_id"]

    peek = client.get(f"{API}/sources/{b_body['source_id']}", headers=shop_a["headers"])
    assert peek.status_code == 404, "越权一律按不存在处理，不暴露这条记录存在"

    file_peek = client.get(f"{API}/sources/{b_body['source_id']}/file",
                           headers=shop_a["headers"])
    assert file_peek.status_code == 404


def test_merchant_client_id_is_forced_to_own_client(client: TestClient, db) -> None:
    """商家传别人的 client_id 也必须被改写成自己的，否则等于开了个跨机构写入口。"""
    from sqlalchemy import select

    from backend.db.models import Client, Script, Source

    shop = _merchant(client, "shop_src_c", "伽马医美")
    other = Client(name="别家", industry="medical_beauty", contact=None, plan="free")
    db.add(other)
    db.commit()

    body = _upload(client, shop["headers"], other.id, _docx(PARAGRAPHS), commit=True)
    source = db.get(Source, body["source_id"])
    assert source.client_id == shop["client_id"], "素材必须落在商家自己机构下"
    rows = db.execute(select(Script).where(Script.source_id == source.id)).scalars().all()
    assert {row.client_id for row in rows} == {shop["client_id"]}


# ---------------------------------------------------------------- 能力清单
def test_formats_endpoint_reports_real_capabilities(client: TestClient, auth_headers: dict) -> None:
    """上传页的能力清单来自注册表，且如实标出缺引擎的格式。"""
    resp = client.get(f"{API}/sources/formats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    by_suffix = {item["suffix"]: item for item in data["formats"]}
    assert by_suffix[".doc"]["available"] is False and "另存为" in by_suffix[".doc"]["note"]
    assert data["modes"] == ["blank", "line", "sentence"]


def test_audio_upload_fails_loudly_when_engine_missing(
        client: TestClient, auth_headers: dict, db, monkeypatch) -> None:
    """没装 ASR 时上传录音必须 422 并说明装什么，绝不能返回"0 条话术"。"""
    import backend.parse.media as media
    from backend.db.models import Client

    account = Client(name="语音机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()
    monkeypatch.setattr(media, "engine_available", lambda name: False)
    monkeypatch.setattr(media, "_to_wav_16k", lambda raw: (b"RIFFfake", 4.0))
    monkeypatch.setattr(media, "_asr_model", lambda: (_ for _ in ()).throw(
        media.ParseError(media.ASR_INSTALL_HINT)))

    resp = client.post(f"{API}/scripts/import", headers=auth_headers,
                       data={"client_id": str(account.id), "commit": "false"},
                       files={"file": ("talk.wav", b"\x00" * 64, "audio/wav")})
    assert resp.status_code == 422
    assert "funasr" in resp.json()["msg"]


# ---------------------------------------------------------------- 智能体侧工具
def test_agent_tool_parse_source_returns_text_with_provenance(
        client: TestClient, auth_headers: dict, db) -> None:
    """parse_source 让 A1 自己取内容：给素材 id 就拿到逐条话术 + 位置。

    这条用例是"智能体调用工具"的实物证据，不是文档里写着支持。
    """
    from backend.db.models import Client
    from backend.mcp_server.server import parse_source
    from backend.parse import ParseError

    account = Client(name="智能体机构", industry="medical_beauty", contact=None, plan="free")
    db.add(account)
    db.commit()
    body = _upload(client, auth_headers, account.id, _docx(PARAGRAPHS), commit=True)

    result = parse_source(body["source_id"], mode="line")
    assert result["source_id"] == body["source_id"]
    assert [item["text"] for item in result["items_detail"]] == PARAGRAPHS
    assert [item["ref"] for item in result["items_detail"]] == ["第1段", "第2段"]

    with pytest.raises(ParseError) as exc:
        parse_source(body["source_id"] + 9999)
    assert "不存在" in str(exc.value)


def test_agent_tool_parse_document_stays_inside_data_dir(monkeypatch, tmp_path) -> None:
    """parse_document 必须锁死在项目 data/ 内，否则等于给智能体一个读 .env 的入口。"""
    from backend.parse import ParseError
    from backend.tools import ingest_tool

    monkeypatch.setattr(ingest_tool, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "poster.txt").write_text("术后零风险，全城最低价", encoding="utf-8")
    (tmp_path / ".env").write_text("JWT_SECRET=leak-me", encoding="utf-8")

    result = ingest_tool.parse_local("poster.txt")
    assert result["items"] == ["术后零风险，全城最低价"]

    for sneaky in ("../.env", "..\\..\\.env", "../data/../.env"):
        with pytest.raises(ParseError) as exc:
            ingest_tool.parse_local(sneaky)
        assert "data/" in str(exc.value)
