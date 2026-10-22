"""Read uploaded resume files without writing them to disk."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader
from docx import Document

SUPPORTED_UPLOAD_SUFFIXES = {".txt", ".md", ".pdf", ".docx", ".csv"}
MIN_EXTRACTED_TEXT_LENGTH = 50


def _validate_text(text: str, filename: str, *, structured: bool = False) -> str:
    text = text.strip()
    if not text:
        raise ValueError(f"{filename}: no extractable text.")
    if not structured and len(text) < MIN_EXTRACTED_TEXT_LENGTH:
        raise ValueError(
            f"{filename}: no extractable text (possibly a scanned PDF); "
            f"extracted only {len(text)} characters."
        )
    return text


def _read_single_document(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return _validate_text(data.decode("utf-8-sig"), filename)
    if suffix == ".pdf":
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        return _validate_text(text, filename)
    if suffix == ".docx":
        document = Document(io.BytesIO(data))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return _validate_text(text, filename)
    raise ValueError(
        f"{filename}: unsupported extension '{suffix or '[none]'}'. "
        "Supported extensions: .txt, .md, .pdf, .docx, .csv."
    )


def _read_csv(filename: str, data: bytes) -> list[tuple[str, str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{filename}: CSV must be UTF-8 encoded.") from exc
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    if "resume_text" not in columns:
        found = ", ".join(columns) if columns else "(none)"
        raise ValueError(
            f"{filename}: missing required column 'resume_text'. Columns found: {found}."
        )
    default_label = Path(filename).stem
    results = []
    for row_number, row in enumerate(reader, start=2):
        label = (row.get("candidate_id") or "").strip() or f"{default_label}-{row_number - 1}"
        resume_text = row.get("resume_text") or ""
        results.append((label, _validate_text(resume_text, f"{filename} row {row_number}")))
    if not results:
        raise ValueError(f"{filename}: CSV contains no resume rows.")
    return results


def read_resume_file(name: str, data: bytes) -> list[tuple[str, str]]:
    """Read one uploaded file as ``(candidate_label, text)`` pairs."""
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        return _read_csv(name, data)
    return [(Path(name).stem, _read_single_document(name, data))]


def read_resume_files(
    files: Iterable[tuple[str, bytes]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Read files independently, returning successful results and errors."""
    results: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    for name, data in files:
        try:
            results.extend(read_resume_file(name, data))
        except (OSError, UnicodeDecodeError, ValueError, Exception) as exc:
            errors.append((name, str(exc)))
    return results, errors
