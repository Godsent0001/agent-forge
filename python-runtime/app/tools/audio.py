"""Audio generation and transcript alignment using Python-native WAV metadata."""

from __future__ import annotations

import asyncio
import shutil
import wave
from pathlib import Path
from typing import Any

from app.infra.paths import data_dir
from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


def _wav_duration(path: str) -> float:
    """Read WAV duration using the standard library; no external media binary."""
    try:
        with wave.open(path, "rb") as audio:
            rate = audio.getframerate()
            return audio.getnframes() / rate if rate else 0.0
    except (OSError, wave.Error):
        return 0.0


class VoiceGeneratorTool(Tool):
    name = "voice_generator"
    description = "Convert character dialogue into speech using Piper TTS."

    def __init__(self, voices_dir: str | None = None):
        self._voices_dir = Path(voices_dir).expanduser().resolve() if voices_dir else data_dir() / "assets" / "voices"

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        text = params.get("dialogue") or params.get("text")
        voice = params.get("voice", "default")
        speed = params.get("speed", 1.0)
        output_path = params.get("output_path") or str(data_dir() / "output" / "voice.wav")

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

        duration = _wav_duration(output_path)
        return to_json_output({
            "audio_path": output_path,
            "duration": duration,
            "sample_rate": 22050,
            "speaker": voice,
        })


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
            duration = _wav_duration(audio_path)
        else:
            duration = params.get("duration", 0.0)
        if duration <= 0:
            raise ToolExecutionError(
                "audio_alignment needs either an existing 'audio_path' (to measure "
                "duration via WAV metadata) or an explicit 'duration' field. Note: this "
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


