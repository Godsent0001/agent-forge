"""Pick an H.264 encoder that the ffmpeg on PATH actually has.

Packaged builds ship an LGPL ffmpeg (scripts/fetch-ffmpeg.mjs), which has
openh264 but not the GPL-only libx264. Development machines usually have a
system ffmpeg with libx264. Tools ask this module for encoder arguments
instead of hard-coding one, so both work and output stays H.264/MP4, which
Chromium (the Electron renderer) and social platforms play everywhere.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache

from app.tools.base import ToolExecutionError

# Most capable first. Hardware encoders come last: they exist only on some
# machines and their quality controls differ.
H264_ENCODERS = ("libx264", "libopenh264", "h264_videotoolbox", "h264_mf", "h264_nvenc", "h264_qsv", "h264_amf")

_ENCODER_LINE = re.compile(r"^\s*V[A-Z.]{5}\s+(\S+)")


@lru_cache(maxsize=4)
def available_video_encoders(ffmpeg: str = "ffmpeg") -> frozenset[str]:
    if shutil.which(ffmpeg) is None:
        return frozenset()
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    names = set()
    # The listing starts with a capability legend (" V..... = Video"); encoders follow "------".
    lines = result.stdout.splitlines()
    separator = next((i for i, line in enumerate(lines) if line.strip().startswith("---")), -1)
    for line in lines[separator + 1:]:
        match = _ENCODER_LINE.match(line)
        if match:
            names.add(match.group(1))
    return frozenset(names)


def h264_encoder(ffmpeg: str = "ffmpeg") -> str:
    available = available_video_encoders(ffmpeg)
    for name in H264_ENCODERS:
        if name in available:
            return name
    raise ToolExecutionError(
        "The installed ffmpeg has no H.264 encoder (looked for "
        + ", ".join(H264_ENCODERS)
        + "). Install an ffmpeg build with libopenh264 or libx264."
    )


def h264_args(*, bitrate: str = "4M", ffmpeg: str = "ffmpeg") -> list[str]:
    """ffmpeg output arguments for H.264 video at roughly the given bitrate.

    libx264 uses constant quality (CRF) and ignores the bitrate; the others are
    rate-controlled, so callers pass a bitrate suited to the output size.
    """
    encoder = h264_encoder(ffmpeg)
    if encoder == "libx264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    return ["-c:v", encoder, "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bitrate, "-pix_fmt", "yuv420p"]


def bitrate_for_height(height: int) -> str:
    """A reasonable H.264 bitrate for the given output height."""
    if height <= 360:
        return "800k"
    if height <= 480:
        return "1500k"
    if height <= 720:
        return "3M"
    if height <= 1080:
        return "6M"
    return "12M"
