from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import quote

from office_app.server.env_loader import load_env_files
from office_app.server.providers.base_provider import BaseProvider, ProviderRequestError


class OcrServiceError(RuntimeError):
    pass


class OcrService:
    TEXT_MIME_PREFIXES = ("text/",)
    TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".json",
        ".csv",
        ".tsv",
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".html",
        ".htm",
        ".xml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".log",
        ".rtf",
    }
    HTML_TAG_RE = re.compile(r"<[^>]+>")
    RTF_CONTROL_RE = re.compile(r"\\[a-zA-Z]+-?\d*(?:\s+)?(?=[^A-Za-z]|$)")
    RTF_SLASH_CONTROL_RE = re.compile(r"/[a-zA-Z]+-?\d*(?:\s+)?(?=[^A-Za-z]|$)")
    RTF_HEX_RE = re.compile(r"\\'[0-9a-fA-F]{2}")
    RTF_UNICODE_RE = re.compile(r"\\u(-?\d+)\??")
    RTF_GROUP_PATTERNS = (
        re.compile(r"\{\\fonttbl(?:[^{}]|\{[^{}]*\})*\}", re.IGNORECASE | re.DOTALL),
        re.compile(r"\{\\colortbl(?:[^{}]|\{[^{}]*\})*\}", re.IGNORECASE | re.DOTALL),
        re.compile(r"\{\\stylesheet(?:[^{}]|\{[^{}]*\})*\}", re.IGNORECASE | re.DOTALL),
        re.compile(r"\{\\info(?:[^{}]|\{[^{}]*\})*\}", re.IGNORECASE | re.DOTALL),
        re.compile(r"\{\\pict(?:[^{}]|\{[^{}]*\})*\}", re.IGNORECASE | re.DOTALL),
        re.compile(r"\{\\object(?:[^{}]|\{[^{}]*\})*\}", re.IGNORECASE | re.DOTALL),
        re.compile(r"\{\\\*\\generator(?:[^{}]|\{[^{}]*\})*\}", re.IGNORECASE | re.DOTALL),
    )

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash-lite",
        timeout_seconds: int = 45,
        fetch_json: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        root_dir = Path(__file__).resolve().parents[2]
        pkg_dir = root_dir / "office_app"
        load_env_files(
            [
                root_dir / ".env",
                root_dir / ".env.local",
                pkg_dir / ".env",
                pkg_dir / ".env.local",
            ]
        )
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model_name = (os.getenv("GEMINI_MODEL") or model_name).strip()
        self.timeout_seconds = timeout_seconds
        self._fetch_json = fetch_json or self._default_fetch_json

    def extract_text(self, *, file_name: str, mime_type: Optional[str], content_bytes: bytes) -> Dict[str, Any]:
        normalized_mime = self._normalized_mime_type(file_name=file_name, mime_type=mime_type)
        suffix = Path(file_name).suffix.lower()

        if self._is_local_text(mime_type=normalized_mime, suffix=suffix):
            text = self._extract_local_text(file_name=file_name, mime_type=normalized_mime, content_bytes=content_bytes)
            return {
                "method": "local_text",
                "mime_type": normalized_mime,
                "text": text,
            }

        if normalized_mime.startswith("image/") or normalized_mime == "application/pdf":
            text = self._extract_with_gemini(file_name=file_name, mime_type=normalized_mime, content_bytes=content_bytes)
            return {
                "method": "gemini_vision",
                "mime_type": normalized_mime,
                "text": text,
            }

        raise OcrServiceError(f"OCR is not available for {file_name} ({normalized_mime}).")

    @staticmethod
    def _normalized_mime_type(*, file_name: str, mime_type: Optional[str]) -> str:
        provided = str(mime_type or "").strip().lower()
        guessed = str(mimetypes.guess_type(file_name)[0] or "").strip().lower()
        # application/octet-stream is generic; prefer extension-based detection when available.
        if provided and provided != "application/octet-stream":
            return provided
        if guessed:
            return guessed
        return provided or "application/octet-stream"

    def _is_local_text(self, *, mime_type: str, suffix: str) -> bool:
        return any(mime_type.startswith(prefix) for prefix in self.TEXT_MIME_PREFIXES) or suffix in self.TEXT_EXTENSIONS

    def _extract_local_text(self, *, file_name: str, mime_type: str, content_bytes: bytes) -> str:
        text = content_bytes.decode("utf-8", errors="replace")
        suffix = Path(file_name).suffix.lower()
        if suffix == ".rtf" or mime_type == "application/rtf":
            return self._strip_rtf(text)
        if suffix in {".html", ".htm", ".xml"} or mime_type in {"text/html", "application/xml", "text/xml"}:
            return self._strip_html(text)
        return text.strip()

    def _extract_with_gemini(self, *, file_name: str, mime_type: str, content_bytes: bytes) -> str:
        if not self.api_key:
            raise OcrServiceError("Gemini API key is not configured for OCR.")

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Extract the readable text from this file. "
                                "Return only the extracted text, with line breaks preserved where possible. "
                                "Do not summarize or explain."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(content_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 2048,
            },
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model_name, safe='')}:generateContent?key={quote(self.api_key, safe='')}"
        )
        data = self._fetch_json(url, payload)
        return self._extract_response_text(data)

    def _default_fetch_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        provider = _GeminiTransport(api_key=self.api_key, model_name=self.model_name, timeout_seconds=self.timeout_seconds)
        return provider._post_json(url, payload)

    @staticmethod
    def _extract_response_text(data: Dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            raise OcrServiceError("Gemini OCR returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [str(part.get("text", "")).strip() for part in parts if isinstance(part, dict) and part.get("text")]
        text = "\n".join([item for item in texts if item]).strip()
        if not text:
            raise OcrServiceError("Gemini OCR returned empty text.")
        return text

    @classmethod
    def _strip_html(cls, text: str) -> str:
        cleaned = cls.HTML_TAG_RE.sub(" ", text)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _strip_rtf(cls, text: str) -> str:
        cleaned = text
        for pattern in cls.RTF_GROUP_PATTERNS:
            previous = None
            while cleaned != previous:
                previous = cleaned
                cleaned = pattern.sub(" ", cleaned)
        cleaned = cls.RTF_HEX_RE.sub(" ", cleaned)
        cleaned = cls.RTF_UNICODE_RE.sub(lambda m: chr((int(m.group(1)) + 65536) % 65536), cleaned)
        cleaned = re.sub(r"\\pard(?![a-z])", "\n\n", cleaned)
        cleaned = re.sub(r"\\par(?![a-z])", "\n\n", cleaned)
        cleaned = re.sub(r"\\line(?![a-z])", "\n", cleaned)
        cleaned = re.sub(r"\\page(?![a-z])", "\n", cleaned)
        cleaned = re.sub(r"\\tab(?![a-z])", "\t", cleaned)
        cleaned = re.sub(r"/(?:pard|par|line|page|tab)(?![a-z])", " ", cleaned)
        cleaned = cls.RTF_CONTROL_RE.sub(" ", cleaned)
        cleaned = cls.RTF_SLASH_CONTROL_RE.sub(" ", cleaned)
        cleaned = cleaned.replace("{", " ").replace("}", " ").replace("\\", " ")
        cleaned = html.unescape(cleaned)
        lines = [re.sub(r"\s+", " ", line).strip() for line in cleaned.splitlines()]
        if lines:
            lines[0] = re.sub(r"^[A-Za-z]\s+(?=[A-Z])", "", lines[0], count=1)
        compacted: list[str] = []
        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank:
                    compacted.append("")
                previous_blank = True
                continue
            compacted.append(line)
            previous_blank = False
        return "\n".join(compacted).strip()



class _GeminiTransport(BaseProvider):
    provider_name = "gemini"

    def generate_response(self, *, system_prompt: str, user_prompt: str, context: Optional[Dict[str, Any]] = None, settings: Optional[Dict[str, Any]] = None):
        raise ProviderRequestError("Not used")
