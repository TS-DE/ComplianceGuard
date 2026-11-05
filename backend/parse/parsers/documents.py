"""文档类解析器：文本 / CSV / Word / Excel / PPT / PDF 文字层。

这一层全是"读文件结构"，不需要模型，所以可以在 CI 里全量跑；图片、扫描件、
录音在 media.py（要下模型，测试里一律用假引擎注入）。

为什么每个解析器都要给 ref/pos：商家事后问"这句违规话是哪来的"，系统必须答到
"第 3 页 / Sheet《话术库》·第 12 行 / 第 4 张幻灯片"，只回一段纯文本等于溯源是摆设。
"""

from __future__ import annotations

import csv
import io

from backend.parse.base import (
    OLE_MAGIC,
    Block,
    Doc,
    ParseError,
    Parser,
    decode_bytes,
    register,
    row_text,
)


class TextParser(Parser):
    """.txt/.md：整篇交给切分层，不在这里预判段落边界（切分模式由用户选）。"""

    suffixes = (".txt", ".md")
    kind = "text"
    engine = "decode"

    def parse(self, raw: bytes, filename: str) -> Doc:
        text = decode_bytes(raw)
        return Doc(filename, self.kind, self.engine, [Block(text)],
                   meta={"chars": len(text)})


class CsvParser(Parser):
    """.csv：一行一块。价目表、话术清单最常见的落盘形态就是 csv。"""

    suffixes = (".csv",)
    kind = "sheet"
    engine = "csv"

    def parse(self, raw: bytes, filename: str) -> Doc:
        text = decode_bytes(raw)
        blocks: list[Block] = []
        try:
            rows = list(csv.reader(io.StringIO(text)))
        except csv.Error as exc:
            raise ParseError(f"CSV 结构异常：{exc}") from None
        for number, row in enumerate(rows, start=1):
            line = row_text(list(row))
            if line:
                blocks.append(Block(line, number, f"第{number}行"))
        return Doc(filename, self.kind, self.engine, blocks, meta={"rows": len(rows)})


class DocxParser(Parser):
    """.docx：按正文真实顺序输出段落与表格行。"""

    suffixes = (".docx",)
    kind = "docx"
    engine = "python-docx"

    def parse(self, raw: bytes, filename: str) -> Doc:
        if raw[:8] == OLE_MAGIC:
            raise ParseError("这是老版 .doc（Word 97-2003）改了扩展名，请另存为 .docx 再上传")
        import docx
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        try:
            document = docx.Document(io.BytesIO(raw))
        except Exception as exc:  # python-docx 对损坏 zip 抛的异常类型不统一
            raise ParseError(f"DOCX 解析失败（文件可能损坏）：{type(exc).__name__}") from None

        blocks: list[Block] = []
        ordinal = 0
        para_no = 0
        table_row = 0
        # 不用 document.paragraphs + document.tables：那样会把所有表格甩到正文末尾，
        # "第 5 段"这种溯源就对不上真实位置了。
        for child in document.element.body.iterchildren():
            if child.tag == qn("w:p"):
                text = Paragraph(child, document).text.strip()
                if not text:
                    continue
                ordinal += 1
                para_no += 1
                blocks.append(Block(text, ordinal, f"第{para_no}段"))
            elif child.tag == qn("w:tbl"):
                for row in Table(child, document).rows:
                    table_row += 1
                    line = row_text([cell.text.strip() for cell in row.cells])
                    if line:
                        ordinal += 1
                        blocks.append(Block(line, ordinal, f"表格第{table_row}行"))
        return Doc(filename, self.kind, self.engine, blocks, meta={"blocks": ordinal})


class SheetParser(Parser):
    """.xlsx / .xls：逐行成块，ref 带 sheet 名（多表文件不说清是哪张表等于没说）。"""

    suffixes = (".xlsx", ".xls")
    kind = "sheet"
    engine = "openpyxl/xlrd"

    def parse(self, raw: bytes, filename: str) -> Doc:
        rows, sheets = self._rows(raw)
        blocks: list[Block] = []
        ordinal = 0
        for sheet, number, values in rows:
            line = row_text(list(values))
            if not line:
                continue
            ordinal += 1
            blocks.append(Block(line, ordinal, f"{sheet}·第{number}行"))
        return Doc(filename, self.kind, self.engine, blocks,
                   meta={"sheets": sheets, "rows": len(rows)})

    @staticmethod
    def _rows(raw: bytes) -> tuple[list[tuple[str, int, list]], list[str]]:
        """统一成 (sheet名, 行号, 单元格列表)。

        用文件头而不是扩展名判断是老 xls 还是 xlsx：
        商家改后缀很常见，按扩展名走会把打不开的锅甩给用户。
        .xls 走 xlrd（2.x 已不再支持 xlsx），.xlsx 走 openpyxl。
        """
        out: list[tuple[str, int, list]] = []
        if raw[:8] == OLE_MAGIC:
            import xlrd

            try:
                book = xlrd.open_workbook(file_contents=raw)
            except Exception as exc:
                raise ParseError(f"XLS 解析失败（文件可能损坏）：{type(exc).__name__}") from None
            for sheet in book.sheets():
                for number in range(sheet.nrows):
                    out.append((sheet.name, number + 1, list(sheet.row_values(number))))
            return out, [sheet.name for sheet in book.sheets()]

        import openpyxl

        try:
            book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as exc:
            raise ParseError(
                "XLSX 解析失败：文件可能损坏，或是老版 .xls 改了扩展名（请另存为 .xlsx）") from None
        try:
            names = list(book.sheetnames)
            for name in names:
                sheet = book[name]
                for number, values in enumerate(sheet.iter_rows(values_only=True), start=1):
                    out.append((name, number, list(values)))
        finally:
            book.close()
        return out, names


class PptxParser(Parser):
    """.pptx：每张幻灯片成块，含表格与演讲者备注。

    备注区是很多机构真正写口播话术的地方，只读正文会漏掉最该审的内容。
    """

    suffixes = (".pptx",)
    kind = "slides"
    engine = "python-pptx"

    def parse(self, raw: bytes, filename: str) -> Doc:
        if raw[:8] == OLE_MAGIC:
            raise ParseError("这是老版 .ppt（PowerPoint 97-2003）改了扩展名，请另存为 .pptx 再上传")
        import pptx

        try:
            presentation = pptx.Presentation(io.BytesIO(raw))
        except Exception as exc:
            raise ParseError(f"PPTX 解析失败（文件可能损坏）：{type(exc).__name__}") from None

        blocks: list[Block] = []
        for number, slide in enumerate(presentation.slides, start=1):
            ref = f"第{number}张幻灯片"
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text.strip()
                    if text:
                        blocks.append(Block(text, number, ref))
                elif shape.has_table:
                    for row in shape.table.rows:
                        line = row_text([cell.text.strip() for cell in row.cells])
                        if line:
                            blocks.append(Block(line, number, ref))
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    blocks.append(Block(notes, number, f"{ref}备注"))
        return Doc(filename, self.kind, self.engine, blocks,
                   meta={"slides": len(presentation.slides)})


class PdfParser(Parser):
    """.pdf：优先读文字层；没有文字层的页判定为扫描页，交给 OCR（未启用则如实说明）。"""

    suffixes = (".pdf",)
    kind = "pdf_text"
    engine = "pdfplumber"

    def parse(self, raw: bytes, filename: str) -> Doc:
        if not raw.startswith(b"%PDF-"):
            raise ParseError("扩展名是 .pdf，但文件内容不是 PDF（可能已损坏）")
        import pdfplumber

        text_blocks: list[Block] = []
        blank_pages: list[int] = []
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                total = len(pdf.pages)
                for number, page in enumerate(pdf.pages, start=1):
                    page_text = (page.extract_text() or "").strip()
                    if page_text:
                        text_blocks.append(Block(page_text, number, f"第{number}页"))
                    else:
                        blank_pages.append(number)
        except Exception as exc:  # pdfminer 的 PDFSyntaxError 等不属于 ValueError
            raise ParseError(f"PDF 解析失败（文件可能损坏或被加密）：{type(exc).__name__}") from None

        if not blank_pages:
            return Doc(filename, self.kind, self.engine, text_blocks, meta={"pages": total})

        warnings: list[str] = []
        scan_blocks = self._ocr_pages(raw, blank_pages, warnings)
        blocks = text_blocks + scan_blocks
        if not blocks:
            raise ParseError(
                f"该 PDF 没有可抽取的文本层（共 {total} 页，全为扫描/图片页），"
                "需要 OCR：请确认已安装 rapidocr-onnxruntime 并配置模型目录")
        blocks.sort(key=lambda block: (block.pos or 0))
        return Doc(filename, "pdf_scan", "pdfplumber+rapidocr", blocks,
                   warnings=warnings,
                   meta={"pages": total, "scanned_pages": blank_pages})

    @staticmethod
    def _ocr_pages(raw: bytes, pages: list[int], warnings: list[str]) -> list[Block]:
        """扫描页走 OCR。引擎缺失时不谎报成功：整本都是扫描页就报错，混排则跳过并警告。"""
        from backend.parse.parsers.media import OCR_MAX_PAGES, ocr_pdf_pages

        if len(pages) > OCR_MAX_PAGES:
            raise ParseError(
                f"扫描页共 {len(pages)} 页，超过单次 {OCR_MAX_PAGES} 页上限，请拆分后分批上传")
        try:
            return ocr_pdf_pages(raw, pages)
        except ParseError as exc:
            warnings.append(f"第 {pages} 页未做 OCR：{exc}")
            return []


class RejectParser(Parser):
    """明确不做的格式也登记进注册表：拒绝理由走同一条派发路径，消息口径不会分叉。"""

    kind = "unsupported"
    engine = "none"

    def __init__(self, suffixes: tuple[str, ...], hint: str) -> None:
        self.suffixes = suffixes
        self.note = self.hint = hint

    def parse(self, raw: bytes, filename: str) -> Doc:
        raise ParseError(f"不支持 {filename}：{self.hint}")


for _parser in (
    TextParser(), CsvParser(), DocxParser(), SheetParser(), PptxParser(), PdfParser(),
    RejectParser((".doc", ".wps"), "老版 Word 二进制格式无法解析，请另存为 .docx 后上传"),
    RejectParser((".ppt",), "老版 PPT 二进制格式无法解析，请另存为 .pptx 后上传"),
    RejectParser((".numbers", ".pages", ".odt", ".key"), "该格式没有可靠的开源解析器，请导出为 docx/xlsx 后上传"),
):
    register(_parser)
