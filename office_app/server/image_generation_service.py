from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from office_app.server.env_loader import load_env_files


class ImageGenerationService:
    def __init__(
        self,
        *,
        env: Optional[Dict[str, str]] = None,
        fetch_json: Optional[Callable[[str, Dict[str, str], Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        if env is None:
            server_dir = Path(__file__).resolve().parent
            pkg_dir = server_dir.parent
            root_dir = pkg_dir.parent
            load_env_files((root_dir / ".env", root_dir / ".env.local", pkg_dir / ".env", pkg_dir / ".env.local"))
            self.env = os.environ
        else:
            self.env = env
        self._fetch_json = fetch_json or self._default_fetch_json

    def _config(self, key: str) -> str:
        return str(self.env.get(key) or "").strip()

    def configured(self) -> bool:
        return bool(self._config("GEMINI_API_KEY"))

    def model_name(self) -> str:
        return self._config("GEMINI_IMAGE_MODEL") or "gemini-3.1-flash-image"

    @staticmethod
    def safe_filename(prompt: str, extension: str = "png") -> str:
        text = re.sub(r"[^A-Za-z0-9]+", "_", str(prompt or "").strip().lower())
        text = text.strip("_")[:48] or "art_department_image"
        return f"{text}.{extension}"

    def generate_image(self, *, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        clean_prompt = str(prompt or "").strip()
        if not clean_prompt:
            raise HTTPException(status_code=400, detail="Image prompt is required.")
        api_key = self._config("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="Image generation is not configured. Set GEMINI_API_KEY.")

        selected_model = str(model or "").strip() or self.model_name()
        payload = {
            "model": selected_model,
            "input": [{"type": "text", "text": clean_prompt}],
        }
        response = self._fetch_json(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            {"x-goog-api-key": api_key, "Content-Type": "application/json"},
            payload,
        )
        image_data, mime_type = self._extract_image(response)
        extension = "jpg" if mime_type in {"image/jpeg", "image/jpg"} else "png"
        return {
            "prompt": clean_prompt,
            "model": selected_model,
            "mime_type": mime_type,
            "filename": self.safe_filename(clean_prompt, extension),
            "content_base64": image_data,
            "raw_response": response,
        }

    @classmethod
    def _extract_image(cls, response: Dict[str, Any]) -> Tuple[str, str]:
        output_image = response.get("output_image")
        if isinstance(output_image, dict):
            data = str(output_image.get("data") or "").strip()
            if data:
                return data, str(output_image.get("mime_type") or output_image.get("mimeType") or "image/png")
        found = cls._find_image_part(response)
        if found:
            return found
        raise HTTPException(status_code=502, detail="Gemini did not return generated image data.")

    @classmethod
    def _find_image_part(cls, value: Any) -> Optional[Tuple[str, str]]:
        if isinstance(value, dict):
            data = str(value.get("data") or value.get("imageBytes") or value.get("image_bytes") or "").strip()
            mime_type = str(value.get("mime_type") or value.get("mimeType") or "").strip()
            if data and (mime_type.startswith("image/") or "image" in value):
                return data, mime_type or "image/png"
            for nested in value.values():
                found = cls._find_image_part(nested)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = cls._find_image_part(item)
                if found:
                    return found
        return None

    @staticmethod
    def _default_fetch_json(url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
        request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(detail).get("error", {}).get("message") or detail
            except Exception:
                message = detail
            raise HTTPException(status_code=502, detail=f"Gemini image generation failed: {message}") from exc
        except URLError as exc:
            raise HTTPException(status_code=503, detail="Gemini image generation is unavailable. Try again shortly.") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Gemini returned an invalid image response.") from exc


def decode_generated_image(content_base64: str) -> bytes:
    return base64.b64decode(content_base64)
