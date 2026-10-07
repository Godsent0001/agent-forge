"""Tool-name rule, implemented once (C-3, C-9)."""
import re

TOOL_NAME_RE = r"^[a-z][a-z0-9_-]{0,63}$"
_MAX_LEN = 64
_BAD = re.compile(r"[^a-z0-9_-]")


def sanitize_tool_name(name: str) -> str:
    """Lower-case, other characters become '_', must start with a letter, at most 64 chars."""
    s = _BAD.sub("_", (name or "").strip().lower())
    if not s or not s[0].isalpha() or not s[0].isascii():
        s = "t_" + s
    return s[:_MAX_LEN]


def dedupe_names(names: list[str]) -> list[str]:
    """['x', 'x', 'x'] -> ['x', 'x_2', 'x_3']. Keeps order; never returns a duplicate."""
    used: set[str] = set()
    out: list[str] = []
    for name in names:
        candidate, n = name, 1
        while candidate in used:
            n += 1
            suffix = f"_{n}"
            candidate = name[: _MAX_LEN - len(suffix)] + suffix
        used.add(candidate)
        out.append(candidate)
    return out
