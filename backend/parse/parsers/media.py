"""需要模型的解析器：海报图片 OCR、扫描版 PDF 页 OCR、语音转写。

与 documents.py 的分工是硬性的：这一层依赖可选引擎，装了才生效。
所以引擎缺失必须是"明确报错 + 给出安装命令"，绝不返回空内容冒充成功——
一段海报识别成"0 条话术"，商家会以为文案没问题，这才是真正的事故。

模型权重一律落在 settings.model_path（项目盘），由 core.config 在导入时
把 MODELSCOPE_CACHE / HF_HOME / TORCH_HOME 指过去。
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

from backend.core.config import settings
from backend.parse.base import (
    AUDIO_MAX_BYTES,
    AUDIO_MAX_SECONDS,
    IMAGE_MAX_BYTES,
    LOW_CONFIDENCE,
    Block,
    Doc,
    ParseError,
    Parser,
    engine_available,
    register,
)
# split_text 住在 split.py（切分与锚定是同一套字符串判据）；这里直接指到叶子模块，
# 不走 backend.parse 门面——门面正在导入本模块才会注册解析器，走门面是循环导入。
from backend.parse.split import split_text

OCR_MAX_PAGES = 20        # 单次最多 OCR 几页：同步接口不设上限就会把请求挂死
OCR_MAX_SIDE = 2200       # 送进 OCR 前的最长边像素，更大只会被内部降采样，慢且不更准
OCR_RENDER_SCALE = 2.8    # PDF 页 72pt → 约 200 DPI，海报小字在这档才认得清
OCR_LINE_TOLERANCE = 14   # 判定"同一行"的纵向容差（像素）：海报文字常有轻微倾斜
OCR_INSTALL_HINT = "未安装 OCR 引擎：python -m pip install rapidocr-onnxruntime"
ASR_INSTALL_HINT = ("未安装语音引擎：python -m pip install funasr modelscope soundfile"
                    "（首次运行会下载 SenseVoiceSmall 约 500MB 到 data/models）")
ASR_SAMPLE_RATE = 16000   # SenseVoice 的训练采样率，喂 44.1kHz 只会让结果变差
_TAG = re.compile(r"<\|[^|>]*\|>")  # SenseVoice 会在文本前后挂 <|zh|><|NEUTRAL|> 这类标记


@lru_cache(maxsize=1)
def _ocr_engine():
    """进程内单例：RapidOCR 初始化要加载 det/rec 两个 ONNX 图，每次请求重建会白等几秒。"""
    if not settings.parse_ocr_enabled:
        raise ParseError("OCR 已在配置中关闭（PARSE_OCR_ENABLED=false）")
    if not engine_available("ocr"):
        raise ParseError(OCR_INSTALL_HINT)
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise ParseError(OCR_INSTALL_HINT) from exc
    try:
        return RapidOCR()
    except Exception as exc:  # 权重缺失、onnxruntime 版本不匹配都从这里冒出来
        raise ParseError(f"OCR 引擎初始化失败：{type(exc).__name__}: {exc}") from None


def _to_bgr(source: object):
    """bytes 或 PIL 图像统一成 OpenCV 的 BGR ndarray，并压到 OCR 合适尺寸。"""
    import cv2
    import numpy as np

    if isinstance(source, (bytes, bytearray, memoryview)):
        array = cv2.imdecode(np.frombuffer(bytes(source), np.uint8), cv2.IMREAD_COLOR)
    else:
        rgb = np.array(source.convert("RGB"))
        array = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if array is None or getattr(array, "size", 0) == 0:
        raise ParseError("图片无法解码（文件可能损坏，或不是受支持的图片格式）")
    height, width = array.shape[:2]
    if max(height, width) > OCR_MAX_SIDE:
        ratio = OCR_MAX_SIDE / max(height, width)
        array = cv2.resize(array, (int(width * ratio), int(height * ratio)),
                           interpolation=cv2.INTER_AREA)
    return array


def _reading_order(detections: list) -> list[tuple[str, float]]:
    """按人眼阅读顺序排：先分行（纵向容差），行内按左边缘排序。

    不排序的后果很具体：海报的"限时特惠 / 术后零风险 / 全城最低价"会被打乱，
    切出来的话术和版面读法对不上，商家没法核对。
    """
    rows = []
    for box, text, score in detections:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        stripped = str(text).strip()
        if stripped:
            rows.append([min(ys), min(xs), stripped, float(score)])
    rows.sort(key=lambda row: row[0])
    lines: list[list] = []
    for row in rows:
        if lines and abs(row[0] - lines[-1][0][0]) <= OCR_LINE_TOLERANCE:
            lines[-1].append(row)
        else:
            lines.append([row])
    ordered: list[tuple[str, float]] = []
    for line in lines:
        line.sort(key=lambda row: row[1])
        ordered.extend((row[2], row[3]) for row in line)
    return ordered


def ocr_blocks(source: object, ref_prefix: str = "OCR块") -> list[Block]:
    """对一张图做 OCR，返回按阅读顺序排列的块；每块带识别置信度。"""
    image = _to_bgr(source)  # 先解码再加载引擎：解码失败不该白等几秒加载 ONNX
    detections, _elapse = _ocr_engine()(image)
    if not detections:
        return []
    blocks: list[Block] = []
    for number, (text, score) in enumerate(_reading_order(detections), start=1):
        blocks.append(Block(text, number, f"{ref_prefix}{number}", round(score, 4)))
    return blocks


def _warn_low_confidence(doc: Doc) -> Doc:
    """置信度低必须说给人听：OCR 认错的"保证"两个字，审查结论会整个反过来。"""
    score = doc.confidence
    if score is not None and score < LOW_CONFIDENCE:
        doc.warnings.append(
            f"识别置信度仅 {score:.0%}，很可能有误读，请对照原始素材人工核对后再采信结论")
    return doc


def _pdf_page_images(raw: bytes, page_numbers: list[int]) -> list[tuple[int, object]]:
    """把指定页渲染成 PIL 图像。用已装好的 pypdfium2（pdfplumber 的渲染后端），不额外引依赖。"""
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(io.BytesIO(raw)) as pdf:
        images = []
        for number in page_numbers[:OCR_MAX_PAGES]:
            page = pdf[number - 1]
            bitmap = page.render(scale=OCR_RENDER_SCALE)
            images.append((number, bitmap.to_pil()))
    return images


def ocr_pdf_pages(raw: bytes, page_numbers: list[int]) -> list[Block]:
    """扫描版 PDF 页 → 渲染 → OCR。ref 仍是"第 N 页"，与文字层页保持同一套溯源口径。

    页数上限由调用方先检查：这一层只负责干活，不负责决定"要不要放弃"。
    """
    blocks: list[Block] = []
    for number, image in _pdf_page_images(raw, page_numbers):
        blocks.extend(ocr_blocks(image, ref_prefix=f"第{number}页"))
    return blocks


class ImageParser(Parser):
    """海报 / 截图 / 照片：整张图交给 OCR。"""

    suffixes = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")
    kind = "image"
    engine = "rapidocr"
    requires = "ocr"
    note = "需要 OCR 引擎（rapidocr-onnxruntime）"
    max_bytes = IMAGE_MAX_BYTES

    def parse(self, raw: bytes, filename: str) -> Doc:
        blocks = ocr_blocks(raw)
        if not blocks:
            raise ParseError("图片里没有识别出文字（可能是纯图海报、分辨率过低或角度倾斜）")
        doc = Doc(filename, self.kind, self.engine, blocks, meta={"blocks": len(blocks)})
        return _warn_low_confidence(doc)


@lru_cache(maxsize=1)
def _asr_model():
    """FunASR AutoModel 单例。首次调用会联网下载权重到项目盘，之后的调用完全离线。"""
    if not settings.parse_asr_enabled:
        raise ParseError("语音已在配置中关闭（PARSE_ASR_ENABLED=false）")
    if not engine_available("asr"):
        raise ParseError(ASR_INSTALL_HINT)
    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise ParseError(ASR_INSTALL_HINT) from exc
    try:
        return AutoModel(model="iic/SenseVoiceSmall", device="cpu", disable_update=True)
    except Exception as exc:
        raise ParseError(
            f"语音模型加载失败（首次运行需下载约 500MB 到 {settings.model_path}）："
            f"{type(exc).__name__}: {exc}") from None


def check_duration(seconds: float) -> float:
    """录音时长闸门。单独成函数是为了让上限这条规则可以被测试直接打到，
    不必伪造一个 5 分钟的音频来间接触发。
    """
    if seconds > AUDIO_MAX_SECONDS:
        raise ParseError(
            f"录音 {seconds:.0f} 秒，超过 {AUDIO_MAX_SECONDS} 秒上限，请截取关键片段后上传")
    return round(seconds, 2)


def _to_wav_16k(raw: bytes) -> tuple[bytes, float]:
    """解码 + 转单声道 + 重采样到 16k，返回 (wav 字节, 时长秒)。

    本机没有 ffmpeg，所以解码只能靠 libsndfile（1.1 起才支持 mp3）和 torchaudio；
    两条路都走不通时如实说明是解码器缺失，而不是甩锅"文件坏了"。
    """
    import numpy as np

    samples, rate = None, 0
    try:
        import soundfile as sf

        samples, rate = sf.read(io.BytesIO(raw), dtype="float32")
    except Exception as exc:
        try:
            import torch
            from torchaudio import load as audio_load

            tensor, rate = audio_load(io.BytesIO(raw))
            samples = tensor.numpy().astype("float32")
        except Exception:
            raise ParseError(
                f"音频解码失败（{type(exc).__name__}）。本机没有可用的解码器："
                "请 python -m pip install soundfile（libsndfile≥1.1 可解 wav/flac/ogg/mp3）；"
                "m4a/aac 还需要系统装有 ffmpeg") from None
    if samples.ndim > 1:  # 多声道取均值：识别模型只吃单声道
        samples = samples.mean(axis=1)
    seconds = check_duration(len(samples) / max(rate, 1))
    if rate != ASR_SAMPLE_RATE:
        import torch
        from torchaudio.functional import resample

        samples = resample(torch.from_numpy(samples), rate, ASR_SAMPLE_RATE).numpy()
    mono = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(ASR_SAMPLE_RATE)
        writer.writeframes(mono.tobytes())
    return buffer.getvalue(), seconds


def _tmp_dir() -> Path:
    """临时 wav 的落盘位置：跟着上传目录走，保证只写项目盘。

    单独成函数是为了让测试能把目录换掉——`settings.upload_path` 是 property，
    在实例上打补丁会直接把测试撞死。
    """
    return settings.upload_path / "tmp"


class AudioParser(Parser):
    """口播 / 客服录音 → 带标点的文本，再按句成块。"""

    suffixes = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac")
    kind = "audio"
    engine = "funasr:sensevoice-small"
    requires = "asr"
    note = "需要语音引擎（funasr + SenseVoiceSmall 约 500MB，落 data/models）与音频解码器（soundfile 或 ffmpeg）"
    max_bytes = AUDIO_MAX_BYTES

    def parse(self, raw: bytes, filename: str) -> Doc:
        wav, seconds = _to_wav_16k(raw)
        # FunASR 的入口按文件路径取音频，所以这里落一个临时 wav。
        # 用 tempfile 而不是自造文件名：并发上传时自造名会互相覆盖，识别结果就串到别人家了。
        tmp_dir = _tmp_dir()
        tmp_dir.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(suffix=".wav", prefix="asr-", dir=tmp_dir)
        tmp_path = Path(name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(wav)
            result = _asr_model().generate(input=str(tmp_path), cache={}, language="auto",
                                           use_itn=True, batch_size_s=60)
        finally:
            tmp_path.unlink(missing_ok=True)
        text = _TAG.sub("", str(result[0].get("text", ""))).strip() if result else ""
        if not text:
            raise ParseError("录音里没有识别出有效语音（可能是纯背景音乐或音量过低）")
        sentences = split_text(text, "sentence")
        blocks = [Block(item, number, f"语音第{number}句")
                  for number, item in enumerate(sentences, start=1)]
        return Doc(filename, self.kind, self.engine, blocks,
                   meta={"chars": len(text), "seconds": seconds})


for _parser in (ImageParser(), AudioParser()):
    register(_parser)
