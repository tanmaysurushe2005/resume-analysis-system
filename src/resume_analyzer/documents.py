"""Read supported resume and job-description document formats."""
from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}


def read_document(path: str | Path) -> str:
    """Return extracted UTF-8 text from a supported document.

    PDF and DOCX parsers are imported lazily so plain-text use does not pay
    their import cost, while missing optional dependencies produce an
    actionable error.
    """
    document_path = Path(path)
    suffix = document_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return document_path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF input requires pypdf. Install dependencies with "
                "'py -m pip install -r requirements.txt'."
            ) from exc
        text = "\n".join(page.extract_text() or "" for page in PdfReader(document_path).pages)
    elif suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError(
                "DOCX input requires python-docx. Install dependencies with "
                "'py -m pip install -r requirements.txt'."
            ) from exc
        text = "\n".join(paragraph.text for paragraph in Document(document_path).paragraphs)
    else:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(
            f"Unsupported document type '{suffix or '[none]'}' for {document_path.name}. "
            f"Supported extensions: {supported}."
        )
    if not text.strip():
        raise ValueError(f"No text could be extracted from {document_path.name}.")
    return text
