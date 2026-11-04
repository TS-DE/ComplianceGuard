"""文档解析层抽象：一种文件类型 = 一个 Parser 子类 + REGISTRY 一行。

为什么要有这一层：商家给的素材是「一整页文档」而不是「一条话术」，
而文档形态永远在增加（docx → 表格 → PPT → 海报图 → 录音）。
if/elif 判断扩展名会在第四个类型到来时失控，所以这里用
`Parser` 抽象 + 注册表：新增格式不改调用方语义（LSP），不改判定器（OCP），
业务层也不 import pdfplumber/cv2 这类实现库（DIP）。

pos 的语义随 kind 变化（同一列在不同素材上含义不同，写清比强行统一好）：
    pdf=页码 / pptx=幻灯片序号 / docx=段落序号 / sheet·csv=行号 /
    image=OCR 文本块序号 / audio=起始毫秒 / text=None
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 解析上限
MAX_BYTES = 8 * 1024 * 1024          # 文档类：8 MB
IMAGE_MAX_BYTES = 12 * 1024 * 1024   # 图片类：12 MB（海报常比文档大）
AUDIO_MAX_BYTES = 30 * 1024 * 1024   # 音频类：30 MB
AUDIO_MAX_SECONDS = 300              # 超过 5 分钟的录音不在能力范围（同步接口会长时间占用）
MAX_CHUNKS = 200                     # 一次最多切多少条话术
MIN_CHARS = 4                        # 4 字起：滤掉"备注""第1页"噪声，又保住"术后零风险"
LOW_CONFIDENCE = 0.60                # OCR 平均置信度低于此值必须提醒人工核对
MODES: tuple[str, ...] = ("blank", "line", "sentence")

# 切分优先级：空行 > 行首序号(1. / 1、 / （1）) > 中文序号(一、) > 项目符号
# 注意：多行模式用编译参数而不是内联 (?m) —— 内联标志只能出现在整个表达式的开头，
# 放在分支中间会抛 "global flags not at the start of the expression"。
_SPLIT = re.compile(
    r"\n\s*\n"
    r"|^(?=\s*(?:\d+[.、)）]|[（(]\d+[)）]|[一二三四五六七八九十]+[、.]|[-*•]\s))",
    re.MULTILINE,
)
# 按句切：语音转写没有空行也没有段落，只有标点。
# 没有这一档，一段 30 秒口播会变成一条超长"话术"，逐条审查和引文定位全都失效。
_SENTENCE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
# 切分后要剥掉的行首序号：序号是文档结构，不是话术内容
_LEADING_NO = re.compile(
    r"^\s*(?:\d+[.、)）]|[（(]\d+[)）]|[一二三四五六七八九十]+[、.]|[-*•])\s*"
)


class ParseError(ValueError):
    """解析失败。继承 ValueError 是为了让既有路由的 `except ValueError` 继续生效。"""


@dataclass(frozen=True)
class Block:
    """文档里的一个自然块（段落 / 表格行 / 一页 / 一张幻灯片 / 一句语音）。

    pos 给机器（排序、统计），ref 给人（"第3页"、"Sheet1·第3行"、"00:32"）。
    刻意分成两个字段：只留 ref 就无法排序，只留 pos 在多 Sheet 表格上说不清是哪张表。
    """

    text: str
    pos: int | None = None
    ref: str | None = None
    confidence: float | None = None


@dataclass
class Doc:
    """一个文件的解析结果。blocks 保留顺序，溯源信息不丢。"""

    filename: str
    kind: str
    engine: str
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """拼成整篇纯文本，供「只看文本」的老调用方使用。"""
        return "\n".join(block.text for block in self.blocks)

    @property
    def confidence(self) -> float | None:
        """全部带置信度块的平均值；纯文本层返回 None（意为「不存在识别误差」）。"""
        scores = [b.confidence for b in self.blocks if b.confidence is not None]
        return round(sum(scores) / len(scores), 4) if scores else None


@dataclass(frozen=True)
class Piece:
    """一条可独立审查的话术，带溯源（来自哪个位置、识别置信度多少）。"""

    text: str
    pos: int | None = None
    ref: str | None = None
    confidence: float | None = None


class Parser(ABC):
    """解析器契约。实现必须：不猜内容、失败即抛 ParseError、不返回空串冒充成功。"""

    suffixes: tuple[str, ...] = ()
    kind: str = "text"
    engine: str = "unknown"
    max_bytes: int = MAX_BYTES
    # 需要的可选引擎（"ocr"/"asr"）。能力探测靠它告诉前端"这个格式现在到底能不能吃"，
    # 免得界面写着支持、用户传上来才报"未安装"。
    requires: str | None = None
    # 面向用户的说明：不支持的格式写"怎么办"，需要引擎的格式写"装什么"。
    note: str = ""

    def accepts(self, suffix: str) -> bool:
        return suffix.lower() in self.suffixes

    @abstractmethod
    def parse(self, raw: bytes, filename: str) -> Doc:
        """把字节流解析成 Doc。

        抛出 ParseError 的三种正当场景：文件损坏、格式与扩展名不符、
        需要的引擎未安装。不允许静默返回空内容。
        """


REGISTRY: dict[str, Parser] = {}


def register(parser: Parser) -> None:
    """按扩展名登记解析器。新格式 = 一个子类 + 一行 register()，不改派发逻辑。"""
    for suffix in parser.suffixes:
        REGISTRY[suffix] = parser


def supported_suffixes() -> list[str]:
    """当前真实可解析的扩展名。必须排除 RejectParser：它也在注册表里（统一拒绝口径），
    但把 .doc 算进"支持列表"会让接口和界面都在说谎。
    """
    return sorted(s for s, p in REGISTRY.items() if p.kind != "unsupported")


def engine_available(name: str | None) -> bool:
    """可选引擎是否装了（只看导入性，绝不加载模型——加载一次要几秒到几十秒）。"""
    if not name:
        return True
    from importlib.util import find_spec

    module = {"ocr": "rapidocr_onnxruntime", "asr": "funasr"}.get(name, name)
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):  # 父包缺失时 find_spec 会抛，不算可用
        return False


def capabilities() -> dict[str, object]:
    """当前真实能力：给前端上传提示、给 MCP 工具自检、给 RUNBOOK 排障。

    刻意做成"从注册表算出来"而不是手写一份清单：手写清单一定会和代码不同步，
    不同步的说明书比没有说明书更坏。
    """
    formats = []
    for suffix, parser in sorted(REGISTRY.items()):
        formats.append({
            "suffix": suffix,
            "kind": parser.kind,
            "engine": parser.engine,
            "requires": parser.requires,
            # 注册表里有 ≠ 能解析：拒绝类格式与缺引擎的格式都必须报"吃不下"，
            # 否则前端的 accept 属性会把不该让用户传的文件类型放进来。
            "available": parser.kind != "unsupported" and engine_available(parser.requires),
            "note": parser.note,
            "max_mb": round(parser.max_bytes / 1024 / 1024, 1),
        })
    return {
        "formats": formats,
        "modes": list(MODES),
        "engines": {name: engine_available(name) for name in ("ocr", "asr")},
        "limits": {"max_bytes": MAX_BYTES, "max_chunks": MAX_CHUNKS,
                   "min_chars": MIN_CHARS, "audio_max_seconds": AUDIO_MAX_SECONDS},
    }


def decode_bytes(raw: bytes) -> str:
    """按 UTF-8(BOM) → UTF-8 → GB18030 依次尝试，兼容 Windows 记事本产物。"""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("文本编码无法识别（已尝试 UTF-8 / GB18030）")


# Word 97-2003 / Excel 97-2003 的复合文档头。放在 base 是因为三个解析器都要靠它
# 判断"扩展名在撒谎"，而不是让底层库抛一个用户看不懂的异常。
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def cell_text(value: object) -> str:
    """单元格转文字：整数不带 .0，日期不带时分秒噪声，布尔按中文口径。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date, time)):
        return value.strftime("%H:%M:%S" if isinstance(value, time) else "%Y-%m-%d")
    return str(value).strip()


def row_text(values: list[object], sep: str = " ") -> str:
    """一行单元格拼成一句话：空单元格丢掉，否则引文里会出现一串连续空格。"""
    return sep.join(part for part in (cell_text(value) for value in values) if part).strip()


def parse_file(filename: str, raw: bytes) -> Doc:
    """按扩展名派发到具体解析器。

    未登记的类型明确拒绝，不做「先当文本读读看」的模糊处理——
    把一个 exe 当文本读出来的乱码进了库，后面的审计统计全是假的。
    """
    suffix = Path(filename or "").suffix.lower()
    parser = REGISTRY.get(suffix)
    if parser is None:
        raise ParseError(
            f"不支持的文件类型 {suffix or '(无扩展名)'}；支持 {', '.join(supported_suffixes())}")
    limit = parser.max_bytes
    if len(raw) > limit:
        raise ParseError(f"文件超过 {limit // 1024 // 1024} MB 上限")
    doc = parser.parse(raw, filename)
    if not doc.text.strip():
        raise ParseError(f"{filename} 解析后没有任何文字内容（可能是空文档或纯图片页）")
    return doc


def _flatten(piece: str) -> str:
    """剥序号、压平换行、去装饰符。内部换行压成空格但保留标点——引文校验要求原文可逐字定位。"""
    flat = _LEADING_NO.sub("", piece)
    flat = re.sub(r"\s+", " ", flat).strip(" \t·•-*")
    return flat


def split_text(text: str, mode: str = "blank") -> list[str]:
    """把整篇文本切成逐条话术：去空段、压平换行、剥序号（过滤与去重交给 dedupe_limit）。

    mode 决定分隔方式：实际素材有三种常见形态，靠猜一定会猜错。
    blank=按空行/行首序号切（一段话术=一个自然段）；line=按单换行切（一行一条）；
    sentence=按句末标点切（语音转写与整段连排的唯一可行切法）。
    """
    if mode not in MODES:
        raise ValueError(f"mode 只能是 {' / '.join(MODES)}")
    if mode == "line":
        chunks: Iterable[str | None] = text.splitlines()
    elif mode == "sentence":
        chunks = _SENTENCE.split(text)
    else:
        chunks = _SPLIT.split(text)
    return [piece for piece in (_flatten(b or "") for b in chunks) if piece]


def dedupe_limit(pieces: list[Piece]) -> list[Piece]:
    """过滤过短 + 去重保序 + 限量；与 split_text 共用同一套判据，两条入口不会切出不同结果。"""
    out: list[Piece] = []
    seen: set[str] = set()
    for piece in pieces:
        if len(piece.text) < MIN_CHARS or piece.text in seen:
            continue
        seen.add(piece.text)
        out.append(piece)
        if len(out) >= MAX_CHUNKS:
            break
    return out


def split_doc(doc: Doc, mode: str = "blank") -> list[Piece]:
    """按文档结构切分：块的边界由解析器给出，块内再按 mode 细分。

    为什么要保留块的 pos：商家问「这句是哪来的」时，必须能答到「第 3 页 / 第 2 张幻灯片」，
    否则溯源字段就是摆设。
    """
    pieces: list[Piece] = []
    for block in doc.blocks:
        for raw_piece in split_text(block.text, mode):
            pieces.append(Piece(raw_piece, block.pos, block.ref, block.confidence))
    return dedupe_limit(pieces)


def split_scripts(text: str, mode: str = "blank") -> list[str]:
    """整篇文本 → 逐条话术。刻意复用 split_doc 这一条路径：
    两个入口若各切一遍，同一份素材会出现「接口和页面结果不一致」这种查不动的 bug。
    """
    whole = Doc(filename="", kind="text", engine="memory", blocks=[Block(text)])
    return [piece.text for piece in split_doc(whole, mode)]


def extract_text(filename: str, raw: bytes) -> str:
    """只要纯文本的调用方用的入口（丢弃溯源，但不会丢弃原文内容）。"""
    return parse_file(filename, raw).text
