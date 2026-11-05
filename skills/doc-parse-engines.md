# S10 · 可选引擎懒加载 + 能力探测由注册表现算

> 状态：已验证 ｜ 最后验证：2026-11-04 ｜ 适用：`backend/parse/`、以及任何"装了第三方模型才生效"的能力

## 场景
一个功能依赖可选的重型引擎（OCR、ASR、PDF 渲染、向量库），装了才可用，没装也要让系统：
① 正常启动；② 界面上如实说"这个格式现在吃不下"；③ 用户传上来时给出**装什么**而不是 `ModuleNotFoundError`。

## 步骤
1. **注册表是唯一真相**：每种格式登记一个 `Parser` 子类，带 `suffixes / kind / engine / requires / note`；
   `requires` 是可选引擎名（`"ocr"` / `"asr"`），`note` 是给用户的说明。
2. **顶层不 import 重库**：模块级只 import 标准库；`cv2 / numpy / rapidocr / funasr` 全部放进函数体。
3. **引擎单例化并前置三道闸**：配置开关 → `engine_available()`（只看导入性）→ 真正的 import。
   前两道闸保证"没装"这种情况连模型加载都不发起。
4. **能力探测函数从注册表现算**，不从文档手抄：`capabilities()` 返回
   `{formats[], modes[], engines{}, limits{}}`；前端 `accept` 属性、上传提示、RUNBOOK 全都吃它。
5. **失败口径固定三句话**：不支持的类型说"支持哪些"；登记了但打不开的说"为什么打不开"；
   缺引擎的说"装什么命令"。**任何情况都不许返回空内容 / `count=0` 冒充成功。**

## 关键代码
```python
# backend/parse/base.py —— 能力探测不手写清单
def engine_available(name: str | None) -> bool:
    if not name:
        return True
    from importlib.util import find_spec
    module = {"ocr": "rapidocr_onnxruntime", "asr": "funasr"}.get(name, name)
    try:
        return find_spec(module) is not None      # 只看导入性，绝不加载模型
    except (ImportError, ValueError):              # 父包缺失时 find_spec 会抛
        return False

def capabilities() -> dict:
    formats = [{"suffix": s, "kind": p.kind, "engine": p.engine, "requires": p.requires,
                # 注册表里有 ≠ 能解析：拒绝类格式与缺引擎的格式都必须报"吃不下"
                "available": p.kind != "unsupported" and engine_available(p.requires),
                "note": p.note} for s, p in sorted(REGISTRY.items())]
    return {"formats": formats, "modes": list(MODES),
            "engines": {n: engine_available(n) for n in ("ocr", "asr")}}

# backend/parse/parsers/media.py —— 三道闸，顺序不能反
@lru_cache(maxsize=1)
def _ocr_engine():
    if not settings.parse_ocr_enabled:
        raise ParseError("OCR 已在配置中关闭（PARSE_OCR_ENABLED=false）")
    if not engine_available("ocr"):
        raise ParseError(OCR_INSTALL_HINT)         # 先问"装没装"，再谈"能不能加载"
    from rapidocr_onnxruntime import RapidOCR      # 重 import 留在函数体内
    return RapidOCR()
```

## 陷阱
1. **`_ocr_engine()(image)` 这种一行写法会先加载引擎再解码图片**：Python 先求值被调用者。
   损坏图片因此白等几秒 ONNX 加载。写成先解码、后取引擎。
2. **`find_spec()` 对缺失的父包会抛 `ModuleNotFoundError`/`ValueError`，不返回 None**：
   不接住的话"能力探测"本身会把请求搞崩。
3. **能力探测函数绝不允许加载模型**：它会被列表页、自检脚本、前端首屏反复调用，
   加载一次是秒级且吃几百 MB 内存。
4. **模型缓存默认写 C 盘**（`~/.cache/modelscope`、`%USERPROFILE%\.paddle`）。
   必须在 `core.config` 导入时就把 `MODELSCOPE_CACHE / HF_HOME / TORCH_HOME` 指到项目盘，
   而且要 `setdefault` 而不是强制覆盖，允许部署方用环境变量改回去。
5. **手写的"支持格式"文档一定会和代码不同步**：不同步的说明书比没有说明书更坏，
   因为它让用户相信传上去能用。前端一律请求 `/sources/formats`。
6. **`RejectParser`（明确不做的格式）也要进注册表**，但 `capabilities()` 必须把它标成
   `available=False` —— 否则"支持列表"里会出现 `.doc`，界面就开始说谎。

## 验证方式
```bash
# ① 能力探测与代码同步（不装 funasr 时 asr 必须 False）
python -X utf8 -c "from backend.parse import capabilities; print(capabilities()['engines'])"
# ② 真跑一次 OCR（不是假引擎）：自造中文海报 → 逐字回查
python -X utf8 -m scripts.verify_parse
# ③ 回归：假引擎测链路，不加载模型，整套仍在秒级
python -X utf8 -m pytest tests/parse tests/test_sources.py -q
```

## 最后验证结果（2026-11-04，本机 py312_env）
- `engines` → `{'ocr': True, 'asr': False}`；可上传列表自动排除 `.doc/.ppt` 与全部音频（asr 未装）。
- `scripts.verify_parse` → `kind=image engine=rapidocr blocks=3 confidence=0.9973`，
  三行中文按阅读顺序还原，逐字回查断言全部通过。
- `pytest tests/parse tests/test_sources.py` → 通过，耗时秒级（未加载任何模型）。
