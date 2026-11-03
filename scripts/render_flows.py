"""把 docs/flows/*.md 里的 Mermaid 代码块渲染成 PNG。

为什么单独写脚本而不是手动画图：
1) Mermaid 源码可版本管理、可 review，图片不能；
2) 流程改了重跑一次就同步，不会出现"图与代码不一致"这种假文档；
3) 渲染走 Kroki 公共接口（POST 纯文本），本机不需要装 Node/Chrome。

失败不会中断整体渲染：某张图网络失败只跳过该图并记录，其余继续。
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW_DIR = ROOT / "docs" / "flows"
IMG_DIR = FLOW_DIR / "img"
KROKI_URL = "https://kroki.io/mermaid/png"
BLOCK = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
TIMEOUT = 60
# Kroki 前置了 Cloudflare：Python 默认 UA 会被拦成 403（error code: 1010），
# 必须伪装成普通浏览器 UA；连续请求之间也要留间隔，否则会被限流。
HEADERS = {
    "Content-Type": "text/plain; charset=utf-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
PAUSE = 2.0
RETRIES = 3


def extract_blocks(markdown: str) -> list[str]:
    """抽出所有 mermaid 代码块内容（按出现顺序）。"""
    return [block.strip() for block in BLOCK.findall(markdown) if block.strip()]


def render(source: str, target: Path) -> int:
    """调用 Kroki 渲染单张图，失败按次数重试，最终仍失败则抛异常。"""
    last: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        request = urllib.request.Request(
            KROKI_URL, data=source.encode("utf-8"), method="POST", headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = response.read()
            if not payload.startswith(b"\x89PNG"):
                raise ValueError("返回内容不是 PNG")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            return len(payload)
        except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(PAUSE * attempt)
    raise RuntimeError(f"重试 {RETRIES} 次仍失败: {type(last).__name__} {last}")


def main(argv: list[str] | None = None) -> int:
    """渲染全部流程图；返回值 >0 表示有图失败（便于 CI 判断）。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="只渲染文件名包含该字符串的文档")
    parser.add_argument("--layout", choices=["td", "lr", "both"], default="td",
                        help="td=竖版(文档嵌入)；lr=横版(幻灯片)；both=两份都出")
    args = parser.parse_args(argv)

    documents = sorted(FLOW_DIR.glob("*.md"))
    if args.only:
        documents = [path for path in documents if args.only in path.name]
    if not documents:
        print("未找到待渲染的 Markdown 文档")
        return 1

    layouts = ["td", "lr"] if args.layout == "both" else [args.layout]
    total = failed = 0
    for document in documents:
        blocks = extract_blocks(document.read_text(encoding="utf-8"))
        if not blocks:
            print(f"  --   {document.name} 无 mermaid 代码块，跳过")
            continue
        for index, source in enumerate(blocks, start=1):
            stem = document.stem if len(blocks) == 1 else f"{document.stem}-{index}"
            for layout in layouts:
                total += 1
                body = source.replace("flowchart TD", f"flowchart {layout.upper()}")
                suffix = "" if layout == "td" else f"-{layout}"
                target = IMG_DIR / f"{stem}{suffix}.png"
                try:
                    size = render(body, target)
                    print(f"  OK   {target.relative_to(ROOT)}  {size:,} 字节")
                except (urllib.error.URLError, ValueError, TimeoutError, OSError, RuntimeError) as exc:
                    failed += 1
                    print(f"  FAIL {document.name} 第 {index} 个图 ({layout}): "
                          f"{type(exc).__name__} {exc}", file=sys.stderr)

    print(f"共 {total} 张图，成功 {total - failed}，失败 {failed}")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
