"""商家素材摄取层：文档/表格/PPT/PDF/图片/录音 → 带溯源的逐条话术。"""

from backend.parse.base import (
    MAX_BYTES,
    MAX_CHUNKS,
    MIN_CHARS,
    MODES,
    Block,
    Doc,
    ParseError,
    Parser,
    Piece,
    REGISTRY,
    capabilities,
    decode_bytes,
    engine_available,
    extract_text,
    parse_file,
    register,
    split_doc,
    split_scripts,
    split_text,
    supported_suffixes,
)

# 导入这两个模块只为把解析器登记进 REGISTRY（副作用导入），所以刻意不起别名、也不进 __all__。
from backend.parse import documents, media  # noqa: F401

__all__ = [
    "Block", "Doc", "MAX_BYTES", "MAX_CHUNKS", "MIN_CHARS", "MODES", "ParseError",
    "Parser", "Piece", "REGISTRY", "capabilities", "decode_bytes", "engine_available",
    "extract_text", "parse_file", "register", "split_doc", "split_scripts",
    "split_text", "supported_suffixes",
]
