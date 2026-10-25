import sys
import types

import pytest

from app.tools import media_codecs, video_clips
from app.tools.base import ToolExecutionError


_REAL_LISTER = media_codecs.available_video_encoders


@pytest.fixture(autouse=True)
def clear_cache():
    _REAL_LISTER.cache_clear()
    yield
    _REAL_LISTER.cache_clear()


def _encoders(monkeypatch, names):
    monkeypatch.setattr(media_codecs, "available_video_encoders", lambda ffmpeg="ffmpeg": frozenset(names))


def test_parses_ffmpeg_encoder_listing(monkeypatch):
    listing = """Encoders:
 V..... = Video
 ------
 V....D libopenh264          OpenH264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
 V.S... mpeg4                MPEG-4 part 2
 A....D aac                  AAC (Advanced Audio Coding)
"""
    monkeypatch.setattr(media_codecs.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(media_codecs.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=listing, returncode=0))
    assert media_codecs.available_video_encoders() == {"libopenh264", "mpeg4"}


def test_prefers_libx264_then_openh264(monkeypatch):
    _encoders(monkeypatch, {"libopenh264", "libx264", "mpeg4"})
    assert media_codecs.h264_args()[:2] == ["-c:v", "libx264"]
    assert "-crf" in media_codecs.h264_args()


def test_lgpl_build_uses_openh264_with_bitrate(monkeypatch):
    _encoders(monkeypatch, {"libopenh264", "mpeg4"})
    args = media_codecs.h264_args(bitrate="3M")
    assert args[:2] == ["-c:v", "libopenh264"]
    assert args[args.index("-b:v") + 1] == "3M"
    assert "-pix_fmt" in args and "-crf" not in args


def test_missing_h264_encoder_is_a_clear_error(monkeypatch):
    _encoders(monkeypatch, {"mpeg4"})
    with pytest.raises(ToolExecutionError, match="no H.264 encoder"):
        media_codecs.h264_args()


@pytest.mark.parametrize("height,expected", [(202, "800k"), (720, "3M"), (1080, "6M"), (2160, "12M")])
def test_bitrate_for_height(height, expected):
    assert media_codecs.bitrate_for_height(height) == expected


def test_section_download_names_the_encoder_for_frame_exact_cuts(monkeypatch, tmp_path):
    _encoders(monkeypatch, {"libopenh264"})
    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            (tmp_path / "clip.mp4").write_bytes(b"mp4")
            return {"id": "x"}

    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = FakeYDL
    utils = types.ModuleType("yt_dlp.utils")
    utils.download_range_func = lambda chapters, ranges: ("ranges", ranges)
    fake.utils = utils
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", utils)

    out = video_clips.yt_dlp_download_section(
        "https://example.com/v", 10.0, 20.0, tmp_path / "clip", {"max_height": 480}, lambda: None)
    assert out.name == "clip.mp4"
    opts = seen["opts"]
    assert opts["force_keyframes_at_cuts"] is True
    output_args = opts["external_downloader_args"]["ffmpeg_o"]
    assert output_args[:2] == ["-c:v", "libopenh264"] and "1500k" in output_args
