"""素材摄取工具：解析 + 落盘 + 建 sources/scripts 记录（含溯源回填）。

放在 tools 层与 db_tool 同级：它同时碰文件系统和仓储，但不做业务判断
（分数、改写、规则命中都不在这里）。

一条刻意的设计：**客户端传回来的 items 只当"选了哪几条"，不当"溯源是什么"**。
提交时会重新解析同一份文件，按文本回填页码/置信度。
否则前端传什么库里就存什么，"第 3 页"这种说法就成了可以被客户端伪造的数据。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core.config import PROJECT_ROOT, settings
from backend.crud.special import scripts as script_repo
from backend.crud.special import sources as source_repo
from backend.parse import Block, Doc, MAX_CHUNKS, ParseError, Piece, parse_file, split_doc
from backend.schemas.business import ScriptCreate

# 整篇文本存库上限（字符）：再长的素材本就不适合一次判读，截断而不是拒绝
FULL_TEXT_STORE_LIMIT = 200_000


@dataclass
class IngestResult:
    """一次解析的完整产物：既够前端预览，也够落库，不需要再算第二遍。

    带着原始字节走：上传请求本来就把它读进了内存，落盘时再读一遍反而是绕路。
    """

    doc: Doc
    raw: bytes
    pieces: list[Piece] = field(default_factory=list)
    parse_ms: int = 0
    sha256: str = ""

    @property
    def size_bytes(self) -> int:
        return len(self.raw)

    def preview(self) -> dict:
        """预览响应：条目带服务端算出的位置与置信度，供页面勾选。

        同时给 `items`（纯字符串数组，既有页面在用）和 `items_detail`（带溯源）：
        后端一次改完契约会让上一版前端当场白屏，两个字段留一版过渡期。
        """
        return {
            "source": self.doc.filename or "text",
            "filename": self.doc.filename,
            "kind": self.doc.kind,
            "engine": self.doc.engine,
            "confidence": self.doc.confidence,
            "warnings": self.doc.warnings,
            "meta": self.doc.meta,
            "parse_ms": self.parse_ms,
            "size_bytes": self.size_bytes,
            "count": len(self.pieces),
            # 预览与入库共用同一个响应形状（预览就是"建了 0 条"），前端不必按 commit 分支
            "created": 0,
            "script_ids": [],
            "items": [piece.text for piece in self.pieces],
            "items_detail": [_detail(self, piece) for piece in self.pieces],
            # 整篇原文：检查页左栏按原文展示，并把命中定位回文档级位置。
            # 命中的 start/end 是相对**单条话术**的下标，而话术经过剥序号与压平空白，
            # 不一定是原文的字面子串——所以必须给整篇，前端才能带上下文指位置。
            "full_text": self.doc.text,
        }


def signature(raw: bytes) -> str:
    """内容指纹。用指纹而不是文件名判重：商家改名重传是同一条素材。"""
    return hashlib.sha256(raw).hexdigest()


def relative_path(filename: str, digest: str) -> str:
    """存储相对路径 YYYYMM/指纹前16位.扩展名（相对 settings.upload_path）。

    用指纹命名而不是原名：原文件名会互相覆盖（谁都传过 report.docx），
    还会把路径分隔符与超长中文名带进文件系统。
    """
    suffix = Path(filename or "").suffix.lower()[:12]
    return f"{datetime.now():%Y%m}/{digest[:16]}{suffix}"


def store(raw: bytes, rel_path: str) -> str:
    """把原始素材写进项目盘并返回相对路径；同一指纹重复写是幂等的。"""
    target = settings.upload_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(raw)
    return rel_path


def resolve_stored(rel_path: str) -> Path:
    """相对路径 → 绝对路径，并挡住越权读取。

    stored_path 来自库里，理论上可被任何写库通道污染成 "../../.env"；
    预览接口不做前缀校验就等于开一个任意文件读取。
    """
    root = settings.upload_path.resolve()
    target = (root / rel_path).resolve()
    # 用 is_relative_to 而不是字符串前缀比较：前者按路径分量判断，
    # 后者会被 "uploads_evil" 这种同前缀的兄弟目录绕过。
    if not target.is_relative_to(root):
        raise ParseError("素材路径不合法")
    if not target.is_file():
        raise ParseError("原始素材文件不在磁盘上（可能已被清理），仅可查解析结果")
    return target


def _detail(result: IngestResult, piece: Piece) -> dict:
    """一条话术的溯源视图，预览与入库共用同一个形状。

    偏移量全部由解析层算好（`backend/parse/split.py`），这里只做两件事：
    按存下来的那份整篇文本裁剪、以及组装响应。
    为什么要裁：锚点是相对 `doc.text` 算的，而库里存的是 `full_text[:LIMIT]`——
    偏移必须和前端手上那份文本对得上，超出截断范围的一律置 None，
    宁可显示"位置未知"，也不能给一个看着对、其实错的位置。
    """
    limit = len(result.doc.text[:FULL_TEXT_STORE_LIMIT])
    spans = [[start, end] for start, end in piece.spans if end <= limit]
    start, end = spans[0] if spans else [None, None]
    if piece.start is not None and piece.end is not None and piece.end <= limit:
        start, end = piece.start, piece.end      # 块内定位更准，优先于整篇搜的第一处
    return {"text": piece.text, "pos": piece.pos, "ref": piece.ref,
            "confidence": piece.confidence, "source_start": start, "source_end": end,
            "source_occurrences": spans}


def parse(filename: str, raw: bytes, mode: str = "blank") -> IngestResult:
    """解析并切分，同时记录耗时——OCR/ASR 的性能证据只能这样顺手攒。"""
    started = time.perf_counter()
    doc = parse_file(filename, raw)
    pieces = split_doc(doc, mode)
    return IngestResult(doc=doc, raw=raw, pieces=pieces,
                        parse_ms=int((time.perf_counter() - started) * 1000),
                        sha256=signature(raw))


def source_fields(result: IngestResult, client_id: int, created_by: int | None,
                  stored_path: str | None, item_count: int) -> dict:
    """组装 sources 行。confidence 为 None 表示文本层，不存在识别误差（不是"0 分"）。"""
    return {
        "client_id": client_id,
        "filename": result.doc.filename,
        "kind": result.doc.kind,
        "engine": result.doc.engine,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "stored_path": stored_path,
        "meta": result.doc.meta,
        "confidence": result.doc.confidence,
        "warnings": result.doc.warnings,
        "parse_ms": result.parse_ms,
        "item_count": item_count,
        # 整篇文本入库存一份：判定要看全局，而重读原始文件会重跑 OCR（单张海报 4 秒起）。
        # 超长截断而不是拒绝——被截掉的部分本来就超过单次审查的合理范围。
        "full_text": result.doc.text[:FULL_TEXT_STORE_LIMIT],
        "created_by": created_by,
    }


def _match(pieces: list[Piece], wanted: list[str]) -> list[Piece]:
    """按文本把勾选的条目对回服务端解析结果，取回它们的溯源。

    匹配不到就报错：宁可拒绝入库，也不写一条"不知道从哪来"的话术进库。
    """
    by_text: dict[str, Piece] = {}
    for piece in pieces:
        by_text.setdefault(piece.text, piece)
    picked: list[Piece] = []
    missing: list[str] = []
    for text in wanted[:MAX_CHUNKS]:
        piece = by_text.get(text)
        if piece is None:
            missing.append(text)
            continue
        picked.append(piece)
    if missing:
        raise ParseError(
            f"有 {len(missing)} 条内容与文件解析结果对不上（第一条：{missing[0][:30]}），"
            "请重新解析预览后再入库")
    return picked


def commit(db: Session, result: IngestResult, client_id: int, scene: str | None,
           user_id: int | None, wanted: list[str] | None = None) -> dict:
    """落库：写原始文件 → 建 sources 行 → 逐条建带溯源的 scripts 行。

    返回 script_ids 供批量审查接着用，顺序与勾选顺序一致。
    中途失败直接抛异常回滚：宁可整批不入库，也不要留下"有素材没话术"的半个状态。
    """
    pieces = _match(result.pieces, wanted) if wanted else result.pieces
    if not pieces:
        raise ParseError("没有可入库的条目")
    stored_path = store(result.raw, relative_path(result.doc.filename, result.sha256))
    source = source_repo.create(db, source_fields(result, client_id, user_id,
                                                  stored_path, len(pieces)))
    created: list[int] = []
    detail: list[dict] = []
    for piece in pieces:
        # 与 service 层同一口径：Repository.create 收的是 dict，不是 Pydantic 对象
        row = script_repo.create(db, ScriptCreate(
            client_id=client_id, scene=scene or None,
            content=piece.text).model_dump())
        item = _detail(result, piece)
        # 溯源在创建之后补写：ScriptCreate 是既有 schema，不为了六个可选字段去改它的校验语义
        script_repo.update(db, row, {"source_id": source.id, "source_pos": piece.pos,
                                     "source_start": item["source_start"],
                                     "source_end": item["source_end"],
                                     "source_ref": piece.ref,
                                     "parse_confidence": piece.confidence})
        created.append(row.id)
        detail.append(dict(item, script_id=row.id))
    return {"source_id": source.id, "created": len(created), "script_ids": created,
            # 提交也回一份带偏移的条目：商家勾完就进结果页，此时还没有"再预览一次"的机会，
            # 少了这份数据，结果页只能退回模糊定位——那正是本阶段要消灭的兜底当主力。
            "items": [piece.text for piece in pieces],
            "items_detail": detail,
            "kind": result.doc.kind, "engine": result.doc.engine,
            "confidence": result.doc.confidence, "warnings": result.doc.warnings,
            "parse_ms": result.parse_ms}


def source_owner(source_id: int) -> dict:
    """素材归属与原名：任何"按 source_id 干活"的入口都要先过这道归属校验。

    单靠调用方传 client_id 不够——那等于让前端自己声明"这份素材是我的"。
    """
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        source = source_repo.get(db, source_id)
        if source is None:
            raise ParseError(f"source {source_id} 不存在")
        return {"client_id": source.client_id, "filename": source.filename,
                "kind": source.kind, "engine": source.engine}


def parse_stored(source_id: int, mode: str = "blank") -> dict:
    """MCP 入口：按素材档案取回原始文件重新解析（只读，不写库）。

    为什么重解析而不是回放库里已有的话术：智能体必须拿到与文件当前内容一致的文字，
    顺手也验证了溯源没有腐坏（文件被清理 / 换版本会在这里立刻暴露）。
    """
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        source = source_repo.get(db, source_id)
        if source is None:
            raise ParseError(f"source {source_id} 不存在")
        path = resolve_stored(source.stored_path)
        result = parse(source.filename, path.read_bytes(), mode)
    payload = result.preview()
    payload["source_id"] = source_id
    return payload


def parse_local(rel_path: str, mode: str = "blank") -> dict:
    """解析项目 data/ 下的素材文件（示例素材、红队海报、自检样本）。

    限定在 data/ 之内并挡掉 ..：MCP 工具一旦被智能体调用，
    不做路径约束就等于给了它一个读 .env 的入口。
    """
    root = (PROJECT_ROOT / "data").resolve()
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root):
        raise ParseError("只允许解析项目 data/ 目录内的素材文件")
    if not target.is_file():
        raise ParseError(f"素材文件不存在：{rel_path}")
    return parse(target.name, target.read_bytes(), mode).preview()


def text_result(text: str, mode: str = "blank") -> IngestResult:
    """粘贴文本走同一条落库路径：kind=text、engine=paste，不留"手工录入就没有溯源"的空档。

    粘贴的内容同样落盘（存的是那段文本本身），商家后来问"这句话哪来的"，
    答案是"你自己 2026-11-04 粘的，原文在这里"，而不是"库里没有记录"。
    """
    doc = Doc(filename="粘贴内容.txt", kind="text", engine="paste",
              blocks=[Block(text)], meta={"chars": len(text)})
    raw = text.encode("utf-8")
    return IngestResult(doc=doc, raw=raw, pieces=split_doc(doc, mode),
                        parse_ms=0, sha256=signature(raw))
