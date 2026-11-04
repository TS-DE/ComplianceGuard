"""文档结构层解析：CSV / Word / Excel / PPT / PDF 文字层。

这些用例全部不碰模型，所以可以在 CI 里全量跑；OCR/ASR 在 test_media.py 用假引擎。
刻意断言 ref（第几页/第几行/第几张幻灯片）与顺序，而不是只断言"抽到了字"：
溯源是这一层存在的理由，字抽错了人还能看出来，位置错了没人会发现。
"""

from __future__ import annotations

import io

import pytest

from backend.parse import ParseError, parse_file, split_doc


def _pdf(pages: list[list[str]]) -> bytes:
    """构造最小合法 PDF：每页一个内容流，Helvetica 只能画 ASCII（真实 PDF 的内嵌中文字体由 pdfplumber 正常处理）。

    xref 偏移按实际字节算：错一个字节 pdfminer 就会报"文件损坏"，
    那样测试证明的是我的构造器有 bug，而不是解析器有问题。
    """
    count = len(pages)
    font_number = 3 + 2 * count
    bodies: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(b"%d 0 R" % (3 + index) for index in range(count))
        + b"] /Count %d >>" % count,
    ]
    for index, lines in enumerate(pages):
        bodies.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (font_number, 3 + count + index))
    for lines in pages:
        stream = b"BT /F1 12 Tf 60 800 Td 16 TL\n"
        for line in lines:
            safe = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            stream += b"(%s) Tj T*\n" % safe.encode("latin-1")
        stream += b"ET"
        bodies.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    bodies.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(bodies) + 1) + b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(bodies) + 1, xref_at))
    return bytes(out)


# ------------------------------------------------------------------ 文本与表格
def test_txt_keeps_whole_content_as_one_block() -> None:
    """.txt 不预判段落边界：切分模式是用户选的，解析器无权替他决定。"""
    doc = parse_file("a.txt", "第一条话术内容。\n\n第二条话术内容。".encode("utf-8"))
    assert doc.kind == "text" and len(doc.blocks) == 1
    assert [p.text for p in split_doc(doc, "blank")] == ["第一条话术内容。", "第二条话术内容。"]


def test_csv_row_becomes_block_with_row_ref() -> None:
    """CSV 一行一块，空单元格不留一串空格进引文。"""
    raw = "话术,场景\n保证做完能白两个度,双眼皮\n,,\n效果因人而异请遵医嘱,热玛吉\n".encode()
    doc = parse_file("price.csv", raw)
    assert [b.ref for b in doc.blocks] == ["第1行", "第2行", "第4行"]
    assert doc.blocks[1].text == "保证做完能白两个度 双眼皮"


def test_xlsx_ref_includes_sheet_name() -> None:
    """多 Sheet 文件不说清是哪张表，等于溯源没做。"""
    import openpyxl

    book = openpyxl.Workbook()
    book.active.title = "话术库"
    book.active.append(["全城最低价"])
    other = book.create_sheet("价目表")
    other.append(["术后零风险", 3800.0])
    buffer = io.BytesIO()
    book.save(buffer)

    doc = parse_file("scripts.xlsx", buffer.getvalue())
    assert doc.meta["sheets"] == ["话术库", "价目表"]
    assert [b.ref for b in doc.blocks] == ["话术库·第1行", "价目表·第1行"]
    # 浮点 3800.0 必须写成 3800：报价话术里的 ".0" 会原样进入引文
    assert doc.blocks[1].text == "术后零风险 3800"


def test_xls_extension_lying_is_resolved_by_file_header() -> None:
    """商家改后缀很常见：按文件头判断，.xls 里装着 xlsx 也要能读，而不是报错甩锅用户。"""
    import openpyxl

    book = openpyxl.Workbook()
    book.active.append(["我们是全城最好的机构"])
    buffer = io.BytesIO()
    book.save(buffer)

    doc = parse_file("old.xls", buffer.getvalue())
    assert doc.blocks[0].text == "我们是全城最好的机构"


# ------------------------------------------------------------------ Word / PPT
def test_docx_keeps_real_body_order_with_paragraph_refs() -> None:
    """段落与表格按正文真实顺序出块。

    python-docx 的 document.paragraphs / document.tables 是两个独立列表，
    直接用会把所有表格甩到最后——"第 3 段"这种溯源就全错位了。
    """
    import docx

    document = docx.Document()
    document.add_paragraph("第一段话术内容足够长")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "表格第一行"
    table.rows[0].cells[1].text = "保证效果"
    table.rows[1].cells[0].text = "表格第二行"
    table.rows[1].cells[1].text = "全城最低"
    document.add_paragraph("第三段话术内容也够长")
    buffer = io.BytesIO()
    document.save(buffer)

    doc = parse_file("talk.docx", buffer.getvalue())
    assert [b.text for b in doc.blocks] == [
        "第一段话术内容足够长", "表格第一行 保证效果", "表格第二行 全城最低",
        "第三段话术内容也够长"]
    assert [b.ref for b in doc.blocks] == ["第1段", "表格第1行", "表格第2行", "第2段"]


def test_docx_that_is_really_old_doc_says_how_to_fix() -> None:
    """.doc 改了扩展名：必须告诉用户"另存为 .docx"，而不是抛底层 zip 异常。"""
    with pytest.raises(ParseError) as exc:
        parse_file("talk.docx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    assert "另存为 .docx" in str(exc.value)


def test_pptx_reads_slide_text_table_and_notes() -> None:
    """幻灯片正文、表格与演讲者备注都要读。

    备注区是机构真正写口播话术的地方，只读正文会漏掉最该审的一段。
    """
    from pptx import Presentation

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "双眼皮限时特惠"
    slide.notes_slide.notes_text_frame.text = "保证做完能往上走三个色度"
    table = slide.shapes.add_table(1, 2, 10, 10, 100, 50).table
    table.cell(0, 0).text = "全城最低价"
    table.cell(0, 1).text = "术后零风险"
    buffer = io.BytesIO()
    deck.save(buffer)

    doc = parse_file("talk.pptx", buffer.getvalue())
    texts = [b.text for b in doc.blocks]
    assert "双眼皮限时特惠" in texts and "保证做完能往上走三个色度" in texts
    assert "全城最低价 术后零风险" in texts
    assert {b.ref for b in doc.blocks} == {"第1张幻灯片", "第1张幻灯片备注"}
    assert doc.meta["slides"] == 1


# ------------------------------------------------------------------ PDF
def test_pdf_text_layer_blocks_by_page() -> None:
    """文字层 PDF：一页一块，ref 是页码。"""
    doc = parse_file("law.pdf", _pdf([["Guaranteed results in seven days"],
                                      ["Our clinic is the best in the city"]]))
    assert doc.kind == "pdf_text" and doc.engine == "pdfplumber"
    assert [b.ref for b in doc.blocks] == ["第1页", "第2页"]
    assert "best in the city" in doc.blocks[1].text


def test_pdf_blank_page_goes_to_ocr_and_keeps_page_ref(monkeypatch) -> None:
    """混排 PDF：第 2 页没有文字层 → 交给 OCR，页码溯源仍是"第2页"，与文字层页同一口径。"""
    import backend.parse.media as media

    def fake_ocr(raw: bytes, pages: list[int]) -> list:
        assert pages == [2]
        return [media.Block("术后零风险 全城最低价", 2, "第2页", 0.93)]

    monkeypatch.setattr(media, "ocr_pdf_pages", fake_ocr)
    doc = parse_file("mix.pdf", _pdf([["Written terms and conditions of the clinic"], []]))
    assert doc.kind == "pdf_scan" and doc.engine == "pdfplumber+rapidocr"
    assert [b.text for b in doc.blocks] == [
        "Written terms and conditions of the clinic", "术后零风险 全城最低价"]
    assert [b.ref for b in doc.blocks] == ["第1页", "第2页"]


def test_pdf_without_ocr_engine_warns_instead_of_faking_success(monkeypatch) -> None:
    """引擎缺失时如实降级：混排文件给出警告并跳过扫描页，整本都是扫描页则明确报错。"""
    import backend.parse.media as media

    def missing(raw: bytes, pages: list[int]) -> list:
        raise ParseError(media.OCR_INSTALL_HINT)

    monkeypatch.setattr(media, "ocr_pdf_pages", missing)
    doc = parse_file("mix.pdf", _pdf([["Terms of the clinic service"], []]))
    assert any("未做 OCR" in item for item in doc.warnings)

    with pytest.raises(ParseError) as exc:
        parse_file("scan.pdf", _pdf([[]]))
    assert "OCR" in str(exc.value)


def test_pdf_with_wrong_extension_is_rejected() -> None:
    """扩展名是 .pdf 但内容不是：说清是文件问题，不让底层库抛看不懂的异常。"""
    with pytest.raises(ParseError) as exc:
        parse_file("not.pdf", b"PK\x03\x04 fake zip content here")
    assert "不是 PDF" in str(exc.value)


def test_legacy_office_formats_are_rejected_with_hint() -> None:
    """.doc/.ppt 走同一条派发路径被拒绝，且注册表里 available=False。"""
    for name in ("a.doc", "a.ppt", "a.odt"):
        with pytest.raises(ParseError) as exc:
            parse_file(name, b"whatever bytes go here")
        assert "请另存为" in str(exc.value) or "请导出为" in str(exc.value)
