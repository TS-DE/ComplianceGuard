"""媒体层解析：图片 OCR、扫描页 OCR、语音转写。

引擎一律用假对象注入——真实 ONNX/模型加载动辄几秒到几十秒，
放进测试会让整套回归变成十分钟的等待；模型是否真能识别，
由 scripts/verify_parse.py 手工验证一次并把结论写进 CHANGELOG。
"""

from __future__ import annotations

import io

import pytest

import backend.parse.media as media
from backend.parse import ParseError, capabilities, parse_file, split_doc


def _png(width: int = 200, height: int = 80) -> bytes:
    """造一张真实可解码的小 PNG：解码链路（cv2）要用真图才测得到。"""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _box(x: float, y: float) -> list:
    return [[x, y], [x + 70, y], [x + 70, y + 14], [x, y + 14]]


@pytest.fixture()
def fake_ocr(monkeypatch):
    """把 OCR 引擎换成可编程的假检出结果。"""
    holder: dict[str, object] = {"detections": []}

    def engine(_image):
        return holder["detections"], [0.01, 0.01, 0.01]

    monkeypatch.setattr(media, "_ocr_engine", lambda: engine)
    return holder


def test_poster_blocks_follow_reading_order(fake_ocr) -> None:
    """海报检测框是打乱的，输出必须按"先上后下、同行先左后右"排。

    不排序的后果很具体：'限时特惠/术后零风险/全城最低价' 被排成乱序，
    切出来的话术和版面读法对不上，商家核对时只会认为系统在读幻觉。
    """
    fake_ocr["detections"] = [
        [_box(10, 40), "全城最低价", 0.88],
        [_box(100, 8), "术后零风险", 0.92],
        [_box(10, 8), "双眼皮限时特惠", 0.95],
    ]
    doc = parse_file("poster.png", _png())
    assert [b.text for b in doc.blocks] == ["双眼皮限时特惠", "术后零风险", "全城最低价"]
    assert [b.ref for b in doc.blocks] == ["OCR块1", "OCR块2", "OCR块3"]
    assert doc.confidence == pytest.approx(0.9167, abs=0.001)
    assert doc.kind == "image" and doc.engine == "rapidocr"


def test_low_confidence_ocr_must_warn_instead_of_lying(fake_ocr) -> None:
    """置信度低必须提醒人工核对：OCR 认错"保证"两个字，审查结论会整个反过来。"""
    fake_ocr["detections"] = [[_box(10, 8), "保 证 做 完 零 风 险", 0.41],
                              [_box(10, 40), "全城最低价哦哦", 0.44]]
    doc = parse_file("blurry.jpg", _png())
    assert any("置信度" in item and "人工核对" in item for item in doc.warnings)


def test_image_without_any_text_fails_loudly(fake_ocr) -> None:
    """纯图海报（没字）不能返回"0 条话术"冒充成功——那等于告诉商家"没问题"。"""
    fake_ocr["detections"] = []
    with pytest.raises(ParseError) as exc:
        parse_file("blank-poster.png", _png())
    assert "没有识别出文字" in str(exc.value)


def test_corrupt_image_says_decode_not_unsupported() -> None:
    """契约变更：图片不再是"不支持"，而是"解不开"，两种说法的处置动作完全不同。"""
    with pytest.raises(ParseError) as exc:
        parse_file("broken.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert "无法解码" in str(exc.value)


def test_ocr_pieces_keep_position_and_confidence(fake_ocr) -> None:
    """溯源必须一路活到话术条目：切分之后每条还知道自己是第几块、置信度多少。"""
    fake_ocr["detections"] = [[_box(10, 8), "保证做完能白两个度", 0.73],
                              [_box(10, 40), "效果因人而异请遵医嘱", 0.91]]
    pieces = split_doc(parse_file("poster.png", _png()), "line")
    assert [(p.text, p.ref, p.confidence) for p in pieces] == [
        ("保证做完能白两个度", "OCR块1", 0.73),
        ("效果因人而异请遵医嘱", "OCR块2", 0.91)]


def test_pdf_pages_render_with_pypdfium2() -> None:
    """扫描页走 OCR 的前提是"能把页渲染成图"，这里只验渲染链路，不碰模型。"""
    from PIL import Image

    from tests.parse.test_documents import _pdf

    images = media._pdf_page_images(_pdf([["Page one"], ["Page two"]]), [2])
    assert [number for number, _ in images] == [2]
    assert isinstance(images[0][1], Image.Image)


# ------------------------------------------------------------------ 语音
class _FakeAsr:
    def __init__(self, text: str) -> None:
        self.text = text
        self.kwargs: dict = {}

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return [{"text": self.text}] if self.text else []


def test_asr_tags_stripped_and_split_by_sentence(monkeypatch, tmp_path) -> None:
    """语音必须按句成块：SenseVoice 的输出带 <|zh|> 这类标记，且整段没有换行。

    没有"按句切"这一档，一段 30 秒口播会变成一条超长话术，
    逐条审查和引文定位全都失效。
    """
    fake = _FakeAsr("<|zh|><|NEUTRAL|><|Speech|>保证做完能往上走三个色度。效果因人而异，请遵医嘱。")
    work_dir = tmp_path / "tmp"
    monkeypatch.setattr(media, "_asr_model", lambda: fake)
    monkeypatch.setattr(media, "_to_wav_16k", lambda raw: (b"RIFFfake", 12.5))
    monkeypatch.setattr(media, "_tmp_dir", lambda: work_dir)

    doc = parse_file("talk.wav", b"x" * 64)
    assert doc.kind == "audio" and doc.meta["seconds"] == 12.5
    assert [b.text for b in doc.blocks] == ["保证做完能往上走三个色度。", "效果因人而异，请遵医嘱。"]
    assert [b.ref for b in doc.blocks] == ["语音第1句", "语音第2句"]
    assert "<|" not in doc.text
    assert fake.kwargs["language"] == "auto" and fake.kwargs["use_itn"] is True
    # 临时 wav 用完必须删：留在目录里会被误当成本轮商家素材
    assert not work_dir.exists() or not list(work_dir.iterdir())


def test_audio_without_engine_gives_install_command(monkeypatch) -> None:
    """没装引擎时报"装什么"，而不是抛 ModuleNotFoundError 让人猜。"""
    monkeypatch.setattr(media, "engine_available", lambda name: False)
    monkeypatch.setattr(media, "_to_wav_16k", lambda raw: (b"RIFFfake", 1.0))
    with pytest.raises(ParseError) as exc:
        parse_file("a.mp3", b"x" * 64)
    assert "funasr" in str(exc.value)


def test_empty_recording_is_not_reported_as_compliant(monkeypatch) -> None:
    """纯背景音乐的录音不能算"识别成功、0 条话术"。"""
    monkeypatch.setattr(media, "_asr_model", lambda: _FakeAsr(""))
    monkeypatch.setattr(media, "_to_wav_16k", lambda raw: (b"RIFFfake", 3.0))
    with pytest.raises(ParseError) as exc:
        parse_file("music.wav", b"x" * 64)
    assert "没有识别出有效语音" in str(exc.value)


def test_long_recording_is_rejected_by_name() -> None:
    """时长上限是硬规则（同步接口会长时间占用），必须能直接打到而不必伪造 5 分钟音频。"""
    assert media.check_duration(3.0) == 3.0
    with pytest.raises(ParseError) as exc:
        media.check_duration(301)
    assert "上限" in str(exc.value)


def test_audio_decode_failure_names_the_missing_decoder() -> None:
    """本机没有 ffmpeg：解码失败要说清哪种格式靠什么解码，而不是甩锅"文件坏了"。"""
    with pytest.raises(ParseError) as exc:
        media._to_wav_16k(b"definitely not a wav file" * 8)
    assert "ffmpeg" in str(exc.value)


# ------------------------------------------------------------------ 能力探测
def test_capabilities_describes_what_is_really_installed() -> None:
    """前端的 accept 列表与提示文案必须由这里出，手写清单一定和代码不同步。"""
    caps = capabilities()
    by_suffix = {item["suffix"]: item for item in caps["formats"]}
    assert by_suffix[".png"]["available"] is True and by_suffix[".png"]["requires"] == "ocr"
    assert by_suffix[".wav"]["requires"] == "asr"
    assert "funasr" in by_suffix[".wav"]["note"]
    # 明确不做的格式：available=False，且 note 告诉用户怎么办
    assert by_suffix[".doc"]["available"] is False and "另存为" in by_suffix[".doc"]["note"]
    assert caps["modes"] == ["blank", "line", "sentence"]
