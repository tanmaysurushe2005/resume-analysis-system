"""Deterministic pre-processing: normalise, neutralise delimiters, detect injection, redact identity."""
from __future__ import annotations

import re
import unicodedata

from .models import IntegrityFlag

MAX_CHARS = 20_000
ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"https?://\S+|(?:www\.|linkedin\.com/|github\.com/)\S+", re.I)
PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{8,}\d(?![\w.])")
PII_LABEL = re.compile(
    r"^\s*(?:date of birth|dob|gender|sex|age|marital status|nationality|religion|"
    r"father'?s name|photo)\b.*$",
    re.I | re.M,
)
INJECTION_PATTERNS = [
    r"ignore (?:all |any |the )*(?:previous|prior|above|earlier) (?:instructions|prompts?|rules)",
    r"disregard (?:all |any |the )*(?:previous|prior|above|earlier)",
    r"\byou are now\b",
    r"\bsystem prompt\b",
    r"(?:rate|score|rank|mark) (?:this|the) candidate",
    r"recommend (?:this candidate|strong advance)",
    r"(?:give|assign) (?:this candidate )?(?:a )?(?:4/4|perfect score|top score)",
    r"</?\s*(?:system|instructions?|resume|assistant|analysis)\s*>",
]
_INJECTION_RE = [re.compile(p, re.I) for p in INJECTION_PATTERNS]


def _redact_phone(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "[PHONE]" if len(digits) >= 10 else m.group(0)  # keeps "2019 - 2022" intact


def sanitize(text: str, redact: bool = True) -> tuple[str, list[IntegrityFlag]]:
    flags: list[IntegrityFlag] = []
    text = unicodedata.normalize("NFKC", text)
    if ZERO_WIDTH.search(text):
        flags.append(IntegrityFlag(type="hidden_text", detail="Zero-width characters found and removed."))
        text = ZERO_WIDTH.sub("", text)

    hits = sorted({m.group(0).strip().lower() for rx in _INJECTION_RE for m in rx.finditer(text)})
    if hits:
        flags.append(IntegrityFlag(
            type="prompt_injection",
            detail="Text addressed to an AI/screening system: " + "; ".join(hits[:3])))

    # Neutralise any attempt to close our XML delimiters.
    text = text.replace("<", "\u2039").replace(">", "\u203a")

    if redact:
        text = EMAIL.sub("[EMAIL]", text)
        text = URL.sub("[LINK]", text)
        text = PHONE.sub(_redact_phone, text)
        text = PII_LABEL.sub("[REDACTED]", text)
        lines = text.strip().splitlines()
        if lines and len(lines[0].split()) <= 5 and not re.search(r"\d", lines[0]):
            lines[0] = "[CANDIDATE]"  # first short line is conventionally the name
            text = "\n".join(lines)

    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        flags.append(IntegrityFlag(type="other", detail=f"Resume truncated to {MAX_CHARS} characters."))
    return text, flags
