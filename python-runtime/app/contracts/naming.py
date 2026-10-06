import re


TOOL_NAME_RE = r"^[a-z][a-z0-9_-]{0,63}$"


def sanitize_tool_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_")
    if not value:
        value = "tool"
    if not value[0].isalpha():
        value = f"tool_{value}"
    return value[:64]


def dedupe_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for raw in names:
        name = sanitize_tool_name(raw)
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name}_{count + 1}")
    return result
