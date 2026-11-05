"""切分与锚定：整篇文本 → 带绝对偏移的逐条话术。

从 base.py 拆出来有两个原因：一是"怎么切"和"切完锚在哪"是同一套字符串判据，
分在两个文件里一定会算出两套下标；二是 base.py 装着解析器契约、注册表、能力探测、
编解码、切分共八件事，已经压过 300 行红线。

切分规则与具体文件格式无关：所有解析器只管交出 Block，怎么切成话术由这里统一决定，
所以文本粘贴入口与文件上传入口不可能切出两种结果。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from backend.parse.base import MAX_CHUNKS, MIN_CHARS, MODES, Block, Doc, Piece

# 一条话术最多列几处出现位置。病态素材（同一句 disclaimer 复制 200 遍）
# 不该把响应撑成几百 KB，超出部分界面本来也只滚动到第一处。
MAX_SPANS = 20

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


def _flatten(piece: str) -> str:
    """剥序号、压平换行、去装饰符。内部换行压成空格但保留标点——引文校验要求原文可逐字定位。"""
    flat = _LEADING_NO.sub("", piece)
    flat = re.sub(r"\s+", " ", flat).strip(" \t·•-*")
    return flat


def split_text(text: str, mode: str = "blank") -> list[str]:
    """把整篇文本切成逐条话术：去空段、压平换行、剥序号（过滤与去重交给 dedupe_limit）。

    三种形态靠猜一定会猜错，所以 mode 由用户选：blank=按空行/行首序号；
    line=按单换行；sentence=按句末标点（语音转写与整段连排的唯一可行切法）。
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
    """过滤过短 + 去重保序 + 限量；与 split_text 共用同一套判据，两条入口不会切出不同结果。

    注意去重是**按文本**的：同一句在素材里出现两遍只会入库一条话术（省掉一次重复审查与
    重复计费）。整篇里那两处文字都还在，所以锚点要给出全部出现位置，
    否则界面只能亮一处，商家看到的还是"写了两遍凭什么只标一遍"。
    """
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


def doc_index(text: str) -> tuple[str, list[int]]:
    """忽略空白的检索串 + 每个检索字符在原串里的下标。"""
    keep, starts = [], []
    for index, char in enumerate(text):
        if not char.isspace():
            keep.append(char)
            starts.append(index)
    return ''.join(keep), starts


def _spans(index: tuple[str, list[int]], needle_text: str,
           base: int = 0, limit: int = MAX_SPANS) -> list[list[int]]:
    """检索串里某个片段的全部出现区间；base 用于把块内下标平移成整篇下标。"""
    hay, starts = index
    needle = ''.join(char for char in needle_text if not char.isspace())
    found: list[list[int]] = []
    at = hay.find(needle) if needle else -1
    while at >= 0 and len(found) < limit and at + len(needle) <= len(starts):
        found.append([base + starts[at], base + starts[at + len(needle) - 1] + 1])
        at = hay.find(needle, at + 1)
    return found


def occurrences(full_text: str, needle_text: str, limit: int = MAX_SPANS) -> list[list[int]]:
    """一句话在整篇文本里的全部出现区间（忽略空白差异）。前端按区间渲染高亮。"""
    return _spans(doc_index(full_text), needle_text, limit=limit)


def split_doc(doc: Doc, mode: str = "blank") -> list[Piece]:
    """按文档结构切分：块的边界由解析器给出，块内再按 mode 细分，并就地算好绝对锚点。

    保留 pos/ref 是因为商家会问"这句是哪来的"，答不到页就等于溯源是摆设；
    start/end 与 spans 是因为 pos 只到"块"这一级，同块内的同款文案它分不开。
    索引整篇算一次、全部条目共用：逐条重扫长文会把预览从毫秒级拖成秒级。
    """
    whole = doc.text
    index = doc_index(whole)          # 整篇一次建好，全部条目共用；逐条重扫就是 O(n²)
    pieces: list[Piece] = []
    base = 0
    for block in doc.blocks:
        local = doc_index(block.text)
        for raw_piece in split_text(block.text, mode):
            in_block = _spans(local, raw_piece, limit=1)
            start, end = (in_block[0] if in_block else (None, None))
            pieces.append(Piece(raw_piece, block.pos, block.ref, block.confidence,
                                start if start is None else start + base,
                                end if end is None else end + base,
                                tuple(tuple(span) for span in _spans(index, raw_piece))))
        base += len(block.text) + 1        # Doc.text 用 "\n" 连接块
    return dedupe_limit(pieces)


def split_scripts(text: str, mode: str = "blank") -> list[str]:
    """整篇文本 → 逐条话术。刻意复用 split_doc 这一条路径：
    两个入口若各切一遍，同一份素材会出现「接口和页面结果不一致」这种查不动的 bug。
    """
    whole = Doc(filename="", kind="text", engine="memory", blocks=[Block(text)])
    return [piece.text for piece in split_doc(whole, mode)]
