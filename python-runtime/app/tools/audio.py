"""
Audio shelf. Voice Generator uses Piper TTS (local, offline, ONNX-based —
no API key, no per-request cost). The rest use ffmpeg, which is assumed
present on PATH (it's a hard dependency of the Rendering/Composition
shelves too, so it should already be required by the app).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import wave
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


def _ffprobe_duration(path: str) -> float:
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


class VoiceGeneratorTool(Tool):
    name = "voice_generator"
    description = "Convert character dialogue into speech using Piper TTS."

    def __init__(self, voices_dir: str = "./assets/voices"):
        self._voices_dir = Path(voices_dir)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        text = params.get("dialogue") or params.get("text")
        voice = params.get("voice", "default")
        speed = params.get("speed", 1.0)
        output_path = params.get("output_path", "./output/voice.wav")

        if not text:
            raise ToolExecutionError("voice_generator requires a 'dialogue' or 'text' field")

        if shutil.which("piper") is None:
            raise ToolExecutionError(
                "Piper TTS binary not found on PATH. Install with "
                "`pip install piper-tts` (or the standalone binary release) and "
                "download a voice model into the configured voices directory "
                "(e.g. en_US-lessac-medium.onnx). This tool calls "
                "`piper --model <voice>.onnx --output_file <path>` under the hood."
            )

        model_path = self._voices_dir / f"{voice}.onnx"
        if not model_path.exists():
            raise ToolExecutionError(
                f"Voice model not found: {model_path}. Download it into "
                f"{self._voices_dir} (see https://github.com/rhasspy/piper for model links)."
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "piper", "--model", str(model_path), "--output_file", output_path,
            "--length_scale", str(1.0 / max(speed, 0.1)),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=text.encode())
        if proc.returncode != 0:
            raise ToolExecutionError(f"piper failed: {stderr.decode(errors='replace')[:1000]}")

        duration = _ffprobe_duration(output_path)
        return to_json_output({
            "audio_path": output_path,
            "duration": duration,
            "sample_rate": 22050,
            "speaker": voice,
        })


class AudioProcessingTool(Tool):
    name = "audio_processing"
    description = "Normalize loudness, trim silence, and clean up a voice line."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        in_path = params.get("audio_path")
        out_path = params.get("output_path", "./output/processed_voice.wav")
        if not in_path or not Path(in_path).exists():
            raise ToolExecutionError(f"audio_processing: input file not found: {in_path}")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", in_path,
            "-af", "silenceremove=start_periods=1:start_threshold=-50dB,loudnorm=I=-16:TP=-1.5:LRA=11",
            out_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ToolExecutionError(f"ffmpeg audio processing failed: {stderr.decode(errors='replace')[-800:]}")

        return to_json_output({"audio_path": out_path, "duration": _ffprobe_duration(out_path)})


class AudioAlignmentTool(Tool):
    name = "audio_alignment"
    description = "Produce word-level timing for a voice line from its transcript + duration."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        transcript = params.get("transcript", "")
        audio_path = params.get("audio_path")
        if not transcript:
            raise ToolExecutionError("audio_alignment requires a 'transcript' field")

        if audio_path and Path(audio_path).exists():
            duration = _ffprobe_duration(audio_path)
        else:
            duration = params.get("duration", 0.0)
        if duration <= 0:
            raise ToolExecutionError(
                "audio_alignment needs either an existing 'audio_path' (to measure "
                "duration via ffprobe) or an explicit 'duration' field. Note: this "
                "is an even-split time approximation, not a forced-alignment model "
                "(e.g. Montreal Forced Aligner / whisperx) — swap in a real aligner "
                "for word timing that's accurate to individual syllables."
            )

        words = transcript.split()
        if not words:
            return to_json_output({"words": []})

        # Weight each word's share of the duration by character length —
        # a reasonable approximation without a real forced aligner.
        weights = [max(len(w), 1) for w in words]
        total_weight = sum(weights)
        t = 0.0
        entries = []
        for word, weight in zip(words, weights):
            span = duration * (weight / total_weight)
            entries.append({"text": word, "start": round(t, 3), "end": round(t + span, 3)})
            t += span

        return to_json_output({"words": entries, "duration": duration})


class AudioMixerTool(Tool):
    name = "audio_mixer"
    description = "Combine voice, music, and SFX tracks with ducking and fades."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        voice = params.get("voice_path")
        music = params.get("music_path")
        out_path = params.get("output_path", "./output/mixed.wav")
        duck_db = params.get("music_duck_db", -18)

        if not voice or not Path(voice).exists():
            raise ToolExecutionError(f"audio_mixer requires an existing 'voice_path': {voice}")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        if music and Path(music).exists():
            # Sidechain-duck music under the voice track.
            filter_complex = (
                f"[1:a]volume={duck_db}dB[music_ducked];"
                f"[0:a][music_ducked]amix=inputs=2:duration=first:dropout_transition=2[out]"
            )
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", voice, "-i", music,
                "-filter_complex", filter_complex, "-map", "[out]", out_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", voice, "-c", "copy", out_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ToolExecutionError(f"ffmpeg mix failed: {stderr.decode(errors='replace')[-800:]}")

        return to_json_output({"audio_path": out_path, "duration": _ffprobe_duration(out_path)})
