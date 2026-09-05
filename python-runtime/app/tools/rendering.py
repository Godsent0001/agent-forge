"""
Rendering shelf. Preview/Final Renderer both drive ffmpeg for real —
the difference is resolution/bitrate, exactly per the spec's stated
purpose (fast iteration vs deliverable quality). Render Queue/Worker
are a simple file-backed job queue — enough for a single-machine
desktop app; swap for a real job broker if you add distributed workers.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


async def _run_ffmpeg_from_image_and_audio(image_path: str, audio_path: str | None,
                                            out_path: str, width: int, height: int, fps: int,
                                            fallback_duration: float = 3.0) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-y", "-loop", "1", "-i", image_path]
    if audio_path and Path(audio_path).exists():
        args += ["-i", audio_path, "-shortest"]
    else:
        # No audio track to bound the duration against — an image loop
        # with no -t/-shortest runs forever. This bit me during testing.
        args += ["-t", str(fallback_duration)]
    args += ["-vf", f"scale={width}:{height}", "-r", str(fps), "-c:v", "libx264",
             "-pix_fmt", "yuv420p", out_path]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise ToolExecutionError("ffmpeg render exceeded 30s — check inputs") from e
    if proc.returncode != 0:
        raise ToolExecutionError(f"ffmpeg render failed: {stderr.decode(errors='replace')[-800:]}")


class PreviewRendererTool(Tool):
    name = "preview_renderer"
    description = "Fast, low-resolution render (360p) for checking timing, captions, camera, and lip-sync."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        image_path = params.get("image_path")  # a composited frame, from composition_engine
        audio_path = params.get("audio_path")
        out_path = params.get("output_path", "./output/preview.mp4")

        if not image_path or not Path(image_path).exists():
            raise ToolExecutionError(f"preview_renderer requires an existing 'image_path': {image_path}")

        await _run_ffmpeg_from_image_and_audio(image_path, audio_path, out_path, width=202, height=360, fps=15)
        return to_json_output({"video_path": out_path, "resolution": "202x360", "fps": 15, "mode": "preview"})


class FinalRendererTool(Tool):
    name = "final_renderer"
    description = "Produce the final deliverable: 1080x1920, 30fps, H.264/AAC."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        image_path = params.get("image_path")
        audio_path = params.get("audio_path")
        out_path = params.get("output_path", "./output/final.mp4")

        if not image_path or not Path(image_path).exists():
            raise ToolExecutionError(f"final_renderer requires an existing 'image_path': {image_path}")

        await _run_ffmpeg_from_image_and_audio(image_path, audio_path, out_path, width=1080, height=1920, fps=30)
        return to_json_output({"video_path": out_path, "resolution": "1080x1920", "fps": 30, "mode": "final"})


class RenderQueueTool(Tool):
    name = "render_queue"
    description = "Queue multiple episodes for rendering, track job status."

    def __init__(self, queue_path: str = "./output/render_queue.json"):
        self._path = Path(queue_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("[]")

    def _load(self) -> list[dict]:
        return json.loads(self._path.read_text())

    def _save(self, jobs: list[dict]) -> None:
        self._path.write_text(json.dumps(jobs, indent=2))

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        action = params.get("action", "list")
        jobs = self._load()

        if action == "enqueue":
            episode_id = params.get("episode_id")
            if not episode_id:
                raise ToolExecutionError("enqueue requires 'episode_id'")
            job = {"id": str(uuid.uuid4()), "episode_id": episode_id, "status": "queued"}
            jobs.append(job)
            self._save(jobs)
            return to_json_output(job)

        if action == "list":
            return to_json_output({"jobs": jobs})

        if action == "update_status":
            job_id, status = params.get("job_id"), params.get("status")
            job = next((j for j in jobs if j["id"] == job_id), None)
            if not job:
                raise ToolExecutionError(f"No such job: {job_id}")
            job["status"] = status
            self._save(jobs)
            return to_json_output(job)

        raise ToolExecutionError(f"Unknown action '{action}'. Use enqueue, list, or update_status.")


class RenderWorkerTool(Tool):
    name = "render_worker"
    description = "Execute a single queued render job end to end."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        job_id = params.get("job_id")
        image_path = params.get("image_path")
        audio_path = params.get("audio_path")
        out_path = params.get("output_path", f"./output/{job_id or 'job'}.mp4")

        if not image_path or not Path(image_path).exists():
            raise ToolExecutionError(f"render_worker requires an existing 'image_path': {image_path}")

        await _run_ffmpeg_from_image_and_audio(image_path, audio_path, out_path, width=1080, height=1920, fps=30)
        return to_json_output({"job_id": job_id, "video_path": out_path, "status": "completed"})
