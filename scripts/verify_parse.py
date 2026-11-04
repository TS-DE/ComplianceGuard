"""解析能力实测：不联网、不花钱，跑真引擎看它到底认不认得出中文。

为什么要单独一个脚本而不是塞进 pytest：
OCR/ASR 加载模型动辄几秒到几十秒，进回归测试会把 5 秒的套件变成 10 分钟；
但"解析层到底能不能用"又必须有人类看得懂的证据，所以放这里手工跑一次、结果写进 CHANGELOG。

用法：
    python -m scripts.verify_parse                    # 自造中文海报，跑真 OCR
    python -m scripts.verify_parse data/x.pdf a.png   # 解析指定素材（含录音，装完 ASR 再验）
"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.parse import capabilities, parse_file, split_doc

# Windows 自带中文字体；一个都没有就不能造中文海报（PIL 默认字体会画出方块，测了等于没测）
CJK_FONTS = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
             r"C:\Windows\Fonts\simsun.ttc"]
LINES = ["双眼皮限时特惠", "保证做完能往上走三个色度", "全城最低价 术后零风险"]


def make_poster(out: Path) -> Path:
    """造一张 900x360 的海报图：三行大字、字号不同，模拟商家真实素材的排版。"""
    from PIL import Image, ImageDraw, ImageFont

    font_path = next((p for p in CJK_FONTS if Path(p).exists()), None)
    if font_path is None:
        raise SystemExit("找不到系统中文字体（msyh/simhei/simsun），无法自造中文海报；"
                         "请改用带参数的形式传入你自己的图片")
    image = Image.new("RGB", (900, 360), (250, 245, 235))
    draw = ImageDraw.Draw(image)
    sizes = (56, 40, 44)
    y = 30
    for text, size in zip(LINES, sizes):
        font = ImageFont.truetype(font_path, size)
        draw.text((40, y), text, fill=(20, 20, 20), font=font)
        y += size + 45
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"[素材] {out}（字体 {Path(font_path).name}，行：{ ' / '.join(LINES)}）")
    return out


def report(path: Path, mode: str = "line") -> None:
    """打印解析结果：引擎、置信度、告警，以及切出来的每条话术带溯源位置。"""
    raw = path.read_bytes()
    doc = parse_file(path.name, raw)
    pieces = split_doc(doc, mode)
    print(f"\n[文件] {path.name}  {len(raw) / 1024:.1f} KB")
    print(f"[结果] kind={doc.kind} engine={doc.engine} "
          f"blocks={len(doc.blocks)} confidence={doc.confidence}")
    for warning in doc.warnings:
        print(f"[警告] {warning}")
    print(f"[溯源] {doc.meta}")
    for piece in pieces[:12]:
        mark = "" if piece.confidence is None else f"  conf={piece.confidence}"
        print(f"  - {piece.ref or '-'}{mark}  {piece.text}")
    if len(pieces) > 12:
        print(f"  … 共 {len(pieces)} 条")
    # 逐字回查：引文校验要求每条话术都能在解析文本里找到，找不到就是解析层在编造
    for piece in pieces:
        assert piece.text.replace(" ", "") in doc.text.replace(" ", ""), f"引文无法定位：{piece.text}"


def main(argv: list[str]) -> int:
    caps = capabilities()
    print(f"[能力] ocr={caps['engines']['ocr']} asr={caps['engines']['asr']} "
          f"modes={caps['modes']}")
    print(f"[可上传] {', '.join(f['suffix'] for f in caps['formats'] if f['available'])}")
    if any(path.endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac")) for path in argv) \
            and not caps["engines"]["asr"]:
        print("[中止] 语音引擎未安装：pip install funasr modelscope soundfile "
              "（模型会落在 data/models，不写 C 盘）")
        return 1
    try:
        if argv:
            for item in argv:
                report(Path(item))
        else:
            report(make_poster(Path("data") / "verify" / "poster.png"))
    except ValueError as exc:  # ParseError 继承 ValueError，这里统一给出人话
        print(f"[失败] {exc}")
        return 1
    print("\n[结论] 解析链路可用（引文均可在原文定位）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
