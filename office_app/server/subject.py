from __future__ import annotations

import re


def _normalize_body(body: str) -> str:
    text = " ".join((body or "").strip().split())
    text = text.strip(" -\t\r\n")
    text = re.sub(r"\s+([?.!,;:])", r"\1", text)
    return text


def _truncate_subject(text: str, limit: int = 72) -> str:
    if len(text) <= limit:
        return text
    candidate = text[: limit + 1].rstrip()
    if " " in candidate:
        candidate = candidate.rsplit(" ", 1)[0].rstrip()
    return f"{candidate}..."


def generate_subject(body: str) -> str:
    """
    Deterministic subject generator based on the memo body text.
    """
    normalized = _normalize_body(body)
    if not normalized:
        return "Memo"

    return _truncate_subject(normalized)
