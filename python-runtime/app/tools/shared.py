"""
Production IR: the shared JSON shape every production tool reads/writes
against (per the spec — not a callable tool itself, the data contract).

Also holds small helpers shared across tool implementations: JSON in/out
parsing for the Tool.execute(str) -> str contract, project-relative path
resolution, and a phoneme-to-viseme table used by lip_sync.
"""

from __future__ import annotations

import json
from typing import Any

from app.tools.base import ToolExecutionError


def parse_json_input(input: str) -> dict[str, Any]:
    if not input.strip():
        return {}
    try:
        return json.loads(input)
    except json.JSONDecodeError as e:
        raise ToolExecutionError(f"Expected JSON input, got invalid JSON: {e}") from e


def to_json_output(data: Any) -> str:
    return json.dumps(data, indent=2)


# A minimal, coarse phoneme -> viseme table. Not a trained model — good
# enough to drive a parameter-based rig (Rive-style continuous mouth
# shapes), not intended to match a full IPA phoneme set.
VISEME_TABLE: dict[str, str] = {
    "p": "M", "b": "M", "m": "M",
    "f": "FV", "v": "FV",
    "th": "TH", "dh": "TH",
    "t": "T", "d": "T", "n": "T", "l": "T",
    "k": "K", "g": "K", "ng": "K",
    "s": "S", "z": "S", "sh": "S", "ch": "S", "j": "S",
    "r": "R",
    "w": "OO", "u": "OO", "oo": "OO",
    "a": "AA", "ah": "AA",
    "e": "EE", "i": "EE", "ee": "EE",
    "o": "OO",
    " ": "REST",
}


def approximate_visemes_for_word(word: str) -> list[str]:
    """
    Crude grapheme-based approximation (no real phonemizer available
    offline in this environment) — walks characters and maps common
    letter groups to viseme categories. Real deployments should swap
    this for actual phoneme output (e.g. from Piper/espeak-ng's
    phonemization step) — see the note in audio.py's AudioAlignmentTool.
    """
    word = word.lower()
    visemes: list[str] = []
    i = 0
    digraphs = ["th", "sh", "ch", "ng", "oo", "ee", "ah"]
    while i < len(word):
        matched = False
        for dg in digraphs:
            if word[i:i + len(dg)] == dg:
                visemes.append(VISEME_TABLE.get(dg, "AA"))
                i += len(dg)
                matched = True
                break
        if not matched:
            ch = word[i]
            visemes.append(VISEME_TABLE.get(ch, "AA") if ch.isalpha() else "REST")
            i += 1
    return visemes or ["REST"]
