"""Prompt loading and rendering. Prompts live in /prompts as versioned, reviewable files."""
from __future__ import annotations

from pathlib import Path

PROMPT_VERSION = "1.0.0"
PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
_SPLIT = "\n=== USER ===\n"


def build(name: str, **values: str) -> tuple[str, str]:
    """Return (system, user) for a prompt file, substituting {{placeholders}}."""
    shared = (PROMPT_DIR / "00_system.md").read_text(encoding="utf-8").strip()
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    task, user = raw.split(_SPLIT, 1)
    for key, val in values.items():
        user = user.replace("{{" + key + "}}", str(val))
    return f"{shared}\n\n{task.strip()}", user.strip()
