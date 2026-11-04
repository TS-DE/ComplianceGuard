"""商家文案导入：把上传的文件或粘贴的整段文本，切成可逐条审查的话术。

为什么单独成模块而不是塞进路由：
切分规则（按空行/序号/项目符号）是纯逻辑，值得单测；路由只管参数与鉴权。

边界（写清楚，避免"看起来支持其实不支持"）：
- 只做 **文本层** 抽取：.txt/.md/.csv/.docx/.pdf
- **不做 OCR**：扫描件 PDF 与图片会明确报错，不猜内容、不返回空串冒充成功
- **不做语音**：需要 ASR 服务，本阶段不引入
"""

from __future__ import annotations

import io
import re
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_CHUNKS = 200
# 4 个字起：既能滤掉"备注""第1页"这类 2 字噪声，又能保住"术后零风险"这种合法短话术。
MIN_CHARS = 4
SUPPORTED = (".txt", ".md", ".csv", ".docx", ".pdf")

# 切分优先级：空行 > 行首序号(1. / 1、 / （1）) > 中文序号(一、) > 项目符号
# 注意：多行模式用编译参数而不是内联 (?m) —— 内联标志只能出现在整个表达式的开头，
# 放在分支中间会抛 "global flags not at the start of the expression"。
_SPLIT = re.compile(
    r"\n\s*\n"
    r"|^(?=\s*(?:\d+[.、)）]|[（(]\d+[)）]|[一二三四五六七八九十]+[、.]|[-*•]\s))",
    re.MULTILINE,
)


def _decode(raw: bytes) -> str:
    """按 UTF-8(BOM) → UTF-8 → GB18030 依次尝试，兼容 Windows 记事本产物。"""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文本编码无法识别（已尝试 UTF-8 / GB18030）")


def _from_docx(raw: bytes) -> str:
    """抽取段落与表格文字；损坏文件统一转成 ValueError，由路由转 422。"""
    import docx

    try:
        document = docx.Document(io.BytesIO(raw))
    except Exception as exc:  # python-docx 对损坏 zip 抛出的异常类型不统一
        raise ValueError(f"DOCX 解析失败（文件可能损坏）：{type(exc).__name__}") from None
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _from_pdf(raw: bytes) -> str:
    """只抽 PDF 文本层；抽不到文字就是扫描件，明确报错而非返回空。"""
    import pdfplumber

    pages: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception as exc:  # pdfminer 的 PDFSyntaxError 等不属于 ValueError
        raise ValueError(
            f"PDF 解析失败（文件可能损坏或被加密）：{type(exc).__name__}") from None
    text = "\n".join(pages)
    if not text.strip():
        raise ValueError("该 PDF 没有可抽取的文本层（可能是扫描件/图片），需要 OCR，本版本不支持")
    return text


def extract_text(filename: str, raw: bytes) -> str:
    """按扩展名抽取纯文本；不支持的类型直接拒绝，不做模糊处理。"""
    if len(raw) > MAX_BYTES:
        raise ValueError(f"文件超过 {MAX_BYTES // 1024 // 1024} MB 上限")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"不支持的文件类型 {suffix or '(无扩展名)'}；" f"支持 {', '.join(SUPPORTED)}")
    if suffix in {".txt", ".md", ".csv"}:
        return _decode(raw)
    if suffix == ".docx":
        return _from_docx(raw)
    return _from_pdf(raw)


# 切分后要剥掉的行首序号：1. / 1、 / （1） / 一、 / 项目符号
_LEADING_NO = re.compile(
    r"^\s*(?:\d+[.、)）]|[（(]\d+[)）]|[一二三四五六七八九十]+[、.]|[-*•])\s*"
)


def split_scripts(text: str, mode: str = "blank") -> list[str]:
    """把整篇文案切成逐条话术：剥序号、去空段、压平换行、去重保序、限量。

    为什么要剥序号：序号是**文档结构**，不是话术内容。留着它会让引文片段
    带上 "1."，既影响观感，也会让"原文逐字可定位"多一层噪声。
    内部换行压成空格但保留标点——引文校验要求原文可逐字定位。
    """
    pieces: list[str] = []
    seen: set[str] = set()
    # mode 决定分隔方式：实际素材有两种常见形态，靠猜一定会猜错。
    # blank=按空行/行首序号切（一段话术=一个自然段）；line=按单换行切（一行一条）。
    if mode not in {"blank", "line"}:
        raise ValueError("mode 只能是 blank 或 line")
    blocks = text.splitlines() if mode == "line" else _SPLIT.split(text)
    for block in blocks:
        if block is None:
            continue
        flat = _LEADING_NO.sub("", block)
        flat = re.sub(r"\s+", " ", flat).strip(" \t·•-*")
        if len(flat) < MIN_CHARS or flat in seen:
            continue
        seen.add(flat)
        pieces.append(flat)
        if len(pieces) >= MAX_CHUNKS:
            break
    return pieces
