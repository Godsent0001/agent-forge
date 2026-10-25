import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.graph import ToolBinding
from app.contracts.tools import ToolError
from app.infra.workspace import RunWorkspace
from app.tools import registry, video_clips
from app.tools.base import ToolExecutionError
from app.tools.catalog import get_catalog_entry
from app.tools.video_clips import (
    Chapter,
    ClipExtractorInput,
    ClipExtractorTool,
    ClipFinderInput,
    ClipFinderTool,
    Segment,
    Transcript,
    TranscriptService,
    VideoTranscriptInput,
    VideoTranscriptTool,
    find_clips,
    format_timestamp,
    normalize_video_url,
    parse_captions,
    parse_timestamp,
    render_outline,
    timestamp_url,
)

URL = "https://www.youtube.com/watch?v=abc123XYZ00"


class _Cancel:
    cancelled = False

    def raise_if_cancelled(self):
        if self.cancelled:
            raise asyncio.CancelledError()


class _Ctx:
    def __init__(self, workspace, config=None):
        self.execution_id = "exec"
        self.project_id = "proj"
        self.span_id = "span"
        self.workspace = workspace
        self.cancel = _Cancel()
        self.config = config or {}


@pytest.fixture()
def workspace(tmp_path):
    return RunWorkspace("exec", root=tmp_path / "run", assets_root=tmp_path / "assets")


@pytest.fixture(autouse=True)
def public_urls(monkeypatch):
    # Hermetic: the SSRF guard resolves DNS; tests use public-looking URLs only.
    monkeypatch.setattr(video_clips, "guard_media_url", lambda url: None)


def _lecture() -> Transcript:
    lines = [
        "welcome back to the channel today we cover three topics",
        "first a quick history of suspension bridges",
        "the golden gate bridge opened in 1937",
        "engineers worried about wind loads on the deck",
        "now let's talk about the tacoma narrows collapse",
        "in 1940 the bridge twisted violently in moderate wind",
        "aeroelastic flutter caused the deck to fail",
        "this collapse changed how engineers model wind",
        "next topic is concrete and how it cures",
        "water and cement react in a process called hydration",
        "curing takes weeks and temperature matters a lot",
        "finally thanks for watching and please subscribe",
    ]
    segments = [Segment(i * 10.0, i * 10.0 + 9.5, text) for i, text in enumerate(lines)]
    return Transcript(
        source=URL, title="Bridges and Concrete", duration=125.0, origin="manual_captions",
        webpage_url=URL, chapters=[Chapter("Intro", 0), Chapter("Bridge failures", 40), Chapter("Concrete", 80)],
        segments=segments,
    )


# --- time helpers ---------------------------------------------------------


@pytest.mark.parametrize("value,expected", [
    (95, 95.0), ("95.5", 95.5), ("1:35", 95.0), ("01:02:03.5", 3723.5), ("0:00:01,250", 1.25),
])
def test_parse_timestamp(value, expected):
    assert parse_timestamp(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", ["-1", "abc", "1:2:3:4", float("nan"), True])
def test_parse_timestamp_rejects_garbage(value):
    with pytest.raises(ValueError):
        parse_timestamp(value)


def test_format_timestamp():
    assert format_timestamp(5) == "0:05"
    assert format_timestamp(3723) == "1:02:03"


# --- caption parsing -------------------------------------------------------


def test_parse_json3_auto_captions():
    raw = json.dumps({"events": [
        {"tStartMs": 0, "dDurationMs": 4000, "id": 1, "wpWinPosId": 1},
        {"tStartMs": 100, "dDurationMs": 3000, "segs": [{"utf8": "hello"}, {"utf8": " world"}]},
        {"tStartMs": 3100, "dDurationMs": 10, "aAppend": 1, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 3200, "dDurationMs": 2000, "segs": [{"utf8": "second &amp; line"}]},
    ]})
    segments = parse_captions(raw, "json3")
    assert [s.text for s in segments] == ["hello world", "second & line"]
    assert segments[0].start == pytest.approx(0.1)
    assert segments[1].end == pytest.approx(5.2)


def test_parse_vtt_collapses_rolling_auto_caption_duplicates():
    raw = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000 align:start position:0%
the<00:00:00.500><c> bridge</c><00:00:01.000><c> collapsed</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
the bridge collapsed

00:00:02.010 --> 00:00:04.000 align:start position:0%
the bridge collapsed
in<00:00:02.500><c> nineteen</c><00:00:03.000><c> forty</c>
"""
    segments = parse_captions(raw, "vtt")
    assert [s.text for s in segments] == ["the bridge collapsed", "in nineteen forty"]
    assert segments[1].start == pytest.approx(2.01)


def test_parse_srt():
    raw = "1\n00:00:01,000 --> 00:00:03,500\nFirst <i>line</i>\n\n2\n00:00:04,000 --> 00:00:06,000\nSecond line\n"
    segments = parse_captions(raw, "srt")
    assert [(s.start, s.end, s.text) for s in segments] == [(1.0, 3.5, "First line"), (4.0, 6.0, "Second line")]


def test_parse_srv3():
    raw = '<timedtext><body><p t="1000" d="2000">Hi <s>there</s></p><p t="4000" d="1000">Bye</p></body></timedtext>'
    segments = parse_captions(raw, "srv3")
    assert [s.text for s in segments] == ["Hi there", "Bye"]


# --- caption track selection --------------------------------------------


def test_track_prefers_manual_then_original_auto_captions():
    info = {
        "language": "en",
        "subtitles": {"live_chat": [{"ext": "json", "url": "x"}]},
        "automatic_captions": {
            "de": [{"ext": "json3", "url": "de"}],
            "en-orig": [{"ext": "vtt", "url": "orig-vtt"}, {"ext": "json3", "url": "orig-json3"}],
            "en": [{"ext": "json3", "url": "translated"}],
        },
    }
    origin, lang, fmt = video_clips._pick_caption_track(info, None)
    assert (origin, lang, fmt["url"]) == ("auto_captions", "en-orig", "orig-json3")

    info["subtitles"]["en-US"] = [{"ext": "vtt", "url": "manual"}]
    origin, lang, fmt = video_clips._pick_caption_track(info, None)
    assert (origin, lang, fmt["url"]) == ("manual_captions", "en-US", "manual")


def test_track_returns_none_without_captions():
    assert video_clips._pick_caption_track({"subtitles": {}, "automatic_captions": {}}, "en") is None


def test_fetch_captions_never_downloads_media(monkeypatch):
    import sys
    import types

    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello there\n"

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            seen["download"] = download
            return {"id": "abc", "title": "T", "duration": 10, "webpage_url": url,
                    "chapters": [{"title": "Start", "start_time": 0, "end_time": 10}],
                    "subtitles": {"en": [{"ext": "vtt", "url": "https://captions.example/en.vtt"}]}}

        def urlopen(self, url):
            seen["caption_url"] = url
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYDL))
    transcript = video_clips.yt_dlp_fetch_captions(URL, None, {"cookies_from_browser": "firefox"})
    assert seen["download"] is False
    assert seen["opts"]["skip_download"] is True
    assert seen["opts"]["cookiesfrombrowser"] == ("firefox",)
    assert seen["caption_url"] == "https://captions.example/en.vtt"
    assert transcript.origin == "manual_captions"
    assert transcript.segments[0].text == "hello there"
    assert transcript.chapters[0].title == "Start"


def test_bot_check_error_explains_cookie_config():
    err = video_clips._friendly_download_error(RuntimeError("Sign in to confirm you're not a bot"))
    assert "cookies_from_browser" in str(err)


# --- transcript service ---------------------------------------------------


def test_service_caches_by_normalized_url(tmp_path, workspace):
    calls = []

    def fetch(url, language, config):
        calls.append(url)
        return _lecture()

    service = TranscriptService(caption_fetcher=fetch, cache_dir=tmp_path / "cache")
    first, hit1 = service.get(URL + "&t=42s&si=track", workspace=workspace)
    second, hit2 = service.get(URL, workspace=workspace)
    assert (hit1, hit2) == (False, True)
    assert len(calls) == 1
    assert second.segments[3].text == first.segments[3].text
    assert normalize_video_url(URL + "&t=42s&utm_source=x") == URL


def test_service_falls_back_to_speech_to_text(tmp_path, workspace):
    downloaded = {}

    def fetch(url, language, config):
        return Transcript(source=url, title="No captions", duration=30, origin="none")

    def download(url, dest, config):
        downloaded["url"] = url
        path = dest / "audio.m4a"
        path.write_bytes(b"audio")
        return path

    def transcribe(path, language, config):
        assert path.name == "audio.m4a"
        return [Segment(0, 3, "spoken words")], "en"

    service = TranscriptService(caption_fetcher=fetch, audio_downloader=download,
                                transcriber=transcribe, cache_dir=tmp_path / "cache")
    transcript, _ = service.get(URL, workspace=workspace)
    assert transcript.origin == "whisper"
    assert transcript.language == "en"
    assert downloaded["url"] == URL

    with pytest.raises(ToolExecutionError, match="allow_speech_to_text"):
        TranscriptService(caption_fetcher=fetch, cache_dir=tmp_path / "c2").get(
            URL, workspace=workspace, allow_speech_to_text=False)


def test_service_transcribes_local_workspace_file(tmp_path, workspace):
    media = workspace.resolve("uploads/talk.mp3")
    media.parent.mkdir(parents=True)
    media.write_bytes(b"fake")
    service = TranscriptService(transcriber=lambda p, lang, cfg: ([Segment(0, 2, "local speech")], "en"),
                                cache_dir=tmp_path / "cache")
    transcript, hit = service.get("uploads/talk.mp3", workspace=workspace)
    assert transcript.segments[0].text == "local speech"
    assert service.get("uploads/talk.mp3", workspace=workspace)[1] is True
    assert hit is False


@pytest.mark.parametrize("source", ["../secret.mp4", "/etc/passwd", "uploads/missing.mp4"])
def test_service_rejects_unsafe_or_missing_local_paths(tmp_path, workspace, source):
    service = TranscriptService(transcriber=lambda *a: ([], None), cache_dir=tmp_path / "cache")
    with pytest.raises(ToolExecutionError):
        service.get(source, workspace=workspace)


def test_service_rejects_non_media_files(tmp_path, workspace):
    path = workspace.resolve("notes.txt")
    path.write_text("x")
    with pytest.raises(ToolExecutionError, match="Unsupported media"):
        TranscriptService(cache_dir=tmp_path / "cache").get("notes.txt", workspace=workspace)


def test_service_applies_ssrf_guard(monkeypatch, tmp_path, workspace):
    def deny(url):
        raise ToolExecutionError("Requests to private or special-use network addresses are not allowed")

    monkeypatch.setattr(video_clips, "guard_media_url", deny)
    service = TranscriptService(caption_fetcher=lambda *a: pytest.fail("must not fetch"), cache_dir=tmp_path / "c")
    with pytest.raises(ToolExecutionError, match="private"):
        service.get("http://10.0.0.5/video.mp4", workspace=workspace)


def test_real_guard_blocks_loopback():
    from app.tools.video_source import guard_media_url

    with pytest.raises(ToolExecutionError):
        guard_media_url("http://127.0.0.1:9000/x.mp4")


# --- ranking -----------------------------------------------------------


def test_find_clips_ranks_the_relevant_moment_first():
    clips = find_clips(_lecture(), "why did the tacoma narrows bridge collapse", max_clips=3,
                       min_seconds=15, max_seconds=40)
    best = clips[0]
    assert 35 <= best.start <= 50
    assert best.end >= 70
    assert best.end - best.start <= 40 + 3
    assert "tacoma" in best.matched_terms
    assert best.chapter == "Bridge failures"
    assert best.score == 1.0


def test_keywords_find_moments_the_query_does_not_name():
    clips = find_clips(_lecture(), "chemistry of setting", keywords=["hydration", "cement", "curing"],
                       max_clips=1, min_seconds=10, max_seconds=30)
    assert clips and 75 <= clips[0].start <= 95
    assert "hydration" in clips[0].excerpt


def test_find_clips_returns_non_overlapping_results():
    clips = find_clips(_lecture(), "bridge wind engineers", max_clips=5, min_seconds=10, max_seconds=20)
    spans = sorted((c.start, c.end) for c in clips)
    for (s1, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 <= s2 + 3.0  # only padding may overlap


def test_find_clips_without_match_and_without_terms():
    assert find_clips(_lecture(), "quantum chromodynamics") == []
    with pytest.raises(ToolExecutionError, match="no searchable words"):
        find_clips(_lecture(), "the and of")


def test_outline_pages_fit_the_tool_result_budget():
    long = Transcript(source="x", segments=[Segment(i * 5.0, i * 5.0 + 5, f"sentence number {i} " * 6)
                                            for i in range(2000)])
    page, nxt = render_outline(long, max_chars=4000)
    assert len(page) <= 4000 and nxt is not None
    assert page.startswith("[0:00]")
    page2, _ = render_outline(long, offset=nxt, max_chars=4000)
    assert page2.startswith("[")
    assert render_outline(long, offset=10**9) == ("", None)


def test_timestamp_url_only_for_youtube():
    assert timestamp_url(URL + "&t=5s", 95.7) == URL + "&t=95s"
    assert timestamp_url("https://vimeo.com/1", 5) is None


# --- tools -------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcript_tool_returns_compact_summary_and_paged_outline(tmp_path, workspace):
    service = TranscriptService(caption_fetcher=lambda *a: _lecture(), cache_dir=tmp_path / "cache")
    tool = VideoTranscriptTool(service=service)
    result = await tool.run(VideoTranscriptInput(source=URL, include_outline=True), _Ctx(workspace))
    payload = json.loads(result.content)
    assert payload["transcript_origin"] == "manual_captions"
    assert payload["chapters"][1] == {"start": "0:40", "title": "Bridge failures"}
    assert "[0:40]" in payload["outline"] or "tacoma" in payload["outline"]
    assert len(result.content) < 6000
    assert workspace.resolve(payload["transcript_path"]).is_file()


@pytest.mark.asyncio
async def test_finder_uses_saved_transcript_without_network(tmp_path, workspace):
    service = TranscriptService(caption_fetcher=lambda *a: _lecture(), cache_dir=tmp_path / "cache")
    summary = json.loads((await VideoTranscriptTool(service=service).run(
        VideoTranscriptInput(source=URL), _Ctx(workspace))).content)

    offline = TranscriptService(caption_fetcher=lambda *a: pytest.fail("no refetch"), cache_dir=tmp_path / "x")
    result = await ClipFinderTool(service=offline).run(
        ClipFinderInput(query="tacoma narrows collapse", transcript_path=summary["transcript_path"], max_clips=2),
        _Ctx(workspace),
    )
    payload = json.loads(result.content)
    assert payload["clips"][0]["rank"] == 1
    assert payload["clips"][0]["link"].endswith("t=" + str(int(payload["clips"][0]["start"])) + "s")
    assert "tacoma" in payload["clips"][0]["excerpt"]


@pytest.mark.asyncio
async def test_finder_reports_hint_when_nothing_matches(tmp_path, workspace):
    service = TranscriptService(caption_fetcher=lambda *a: _lecture(), cache_dir=tmp_path / "cache")
    result = await ClipFinderTool(service=service).run(
        ClipFinderInput(query="quantum chromodynamics", source=URL), _Ctx(workspace))
    payload = json.loads(result.content)
    assert payload["clips"] == [] and "keywords" in payload["hint"]


@pytest.mark.asyncio
async def test_finder_requires_a_source(workspace):
    with pytest.raises(ToolError, match="source or transcript_path"):
        await ClipFinderTool().run(ClipFinderInput(query="x"), _Ctx(workspace))


def test_extractor_input_validation():
    parsed = ClipExtractorInput(source=URL, clips=[{"start": "1:00", "end": "1:30.5"}])
    assert (parsed.clips[0].start, parsed.clips[0].end) == (60.0, 90.5)
    with pytest.raises(ValidationError):
        ClipExtractorInput(source=URL, clips=[])
    with pytest.raises(ValidationError):
        ClipExtractorInput(source=URL, clips=[{"start": "soon", "end": 5}])


@pytest.mark.asyncio
@pytest.mark.parametrize("clips,match", [
    ([{"start": 10, "end": 5}], "end must be after start"),
    ([{"start": 0, "end": 900}], "longer than"),
    ([{"start": i * 600, "end": i * 600 + 590} for i in range(4)], "Total clip length"),
])
async def test_extractor_rejects_bad_ranges(workspace, clips, match):
    with pytest.raises(ToolError, match=match):
        await ClipExtractorTool(section_downloader=lambda *a: pytest.fail("no download")).run(
            ClipExtractorInput(source=URL, clips=clips), _Ctx(workspace))


@pytest.mark.asyncio
async def test_extractor_downloads_only_requested_sections(monkeypatch, tmp_path, workspace):
    monkeypatch.setattr(video_clips.shutil, "which", lambda name: "/usr/bin/" + name)
    calls = []

    def download(url, start, end, out_stem, config, check_cancel):
        check_cancel()
        calls.append((url, start, end, config))
        path = out_stem.with_suffix(".mp4")
        path.write_bytes(b"mp4")
        return path

    service = TranscriptService(caption_fetcher=lambda *a: _lecture(), cache_dir=tmp_path / "cache")
    tool = ClipExtractorTool(section_downloader=download, service=service)
    result = await tool.run(ClipExtractorInput(
        source=URL, subtitles=True,
        clips=[{"start": "0:40", "end": "1:15", "label": "Tacoma collapse!"}, {"start": 80, "end": 110}],
    ), _Ctx(workspace, config={"max_height": 480}))

    assert [(c[1], c[2]) for c in calls] == [(40.0, 75.0), (80.0, 110.0)]
    assert calls[0][3] == {"max_height": 480}
    payload = json.loads(result.content)
    assert payload["clips"][0]["file"] == "clips/01-tacoma-collapse-40s.mp4"
    srt = workspace.resolve(payload["clips"][0]["subtitles"]).read_text()
    assert srt.startswith("1\n00:00:00,000 --> 00:00:09,500\nnow let's talk about the tacoma narrows collapse")
    assert [a.mime for a in result.artifacts].count("video/mp4") == 2


@pytest.mark.asyncio
async def test_extractor_honours_cancellation(monkeypatch, workspace):
    monkeypatch.setattr(video_clips.shutil, "which", lambda name: "/usr/bin/" + name)
    ctx = _Ctx(workspace)
    ctx.cancel.cancelled = True
    with pytest.raises(asyncio.CancelledError):
        await ClipExtractorTool(section_downloader=lambda *a: pytest.fail("no download")).run(
            ClipExtractorInput(source=URL, clips=[{"start": 0, "end": 5}]), ctx)


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="needs ffmpeg")
async def test_extractor_cuts_local_file_with_ffmpeg(workspace):
    source = workspace.resolve("uploads/sample.mp4")
    source.parent.mkdir(parents=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source),
    ], check=True)
    result = await ClipExtractorTool().run(
        ClipExtractorInput(source="uploads/sample.mp4", clips=[{"start": 1, "end": 3.5}]), _Ctx(workspace))
    clip = workspace.resolve(json.loads(result.content)["clips"][0]["file"])
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=True).stdout)
    assert duration == pytest.approx(2.5, abs=0.3)


# --- wiring ------------------------------------------------------------


@pytest.mark.parametrize("kind,cls", [
    ("video_transcript", VideoTranscriptTool),
    ("clip_finder", ClipFinderTool),
    ("clip_extractor", ClipExtractorTool),
])
def test_registry_builds_native_tools_with_binding_config(kind, cls):
    built = registry.DefaultToolFactory().build(
        ToolBinding(id="t", kind=kind, name=kind, config={"cookies_from_browser": "chrome"}))
    assert isinstance(built, cls)
    assert built.binding_config == {"cookies_from_browser": "chrome"}
    assert get_catalog_entry(kind) is not None
    assert "properties" in cls.Input.model_json_schema()


def test_cookie_config_is_validated():
    assert "cookiesfrombrowser" not in video_clips._ydl_base_opts({"cookies_from_browser": "chrome; rm -rf"})
    assert video_clips._ydl_base_opts({"cookies_from_browser": "edge"})["cookiesfrombrowser"] == ("edge",)


def test_whisper_missing_dependency_has_install_hint(monkeypatch, tmp_path):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ToolExecutionError, match="uv sync --extra transcribe"):
        video_clips.faster_whisper_transcribe(Path(tmp_path / "a.wav"), None, {})
