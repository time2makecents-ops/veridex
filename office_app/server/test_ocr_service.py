from __future__ import annotations

import unittest

from office_app.server.ocr_service import OcrService


class OcrServiceTests(unittest.TestCase):
    def test_extracts_plain_text_locally(self) -> None:
        service = OcrService(api_key="")
        result = service.extract_text(
            file_name="notes.txt",
            mime_type="text/plain",
            content_bytes=b"hello world",
        )
        self.assertEqual(result["method"], "local_text")
        self.assertEqual(result["text"], "hello world")

    def test_extracts_rtf_locally(self) -> None:
        service = OcrService(api_key="")
        rtf = br"{\rtf1\ansi{\fonttbl{\f0 Calibri;}}{\*\generator Riched20 10.0.19041;}\pardDear Hiring Committee,\parThis is \b bold\b0\par Second line /p /line}"
        result = service.extract_text(
            file_name="memo.rtf",
            mime_type="application/rtf",
            content_bytes=rtf,
        )
        self.assertNotIn("Calibri", result["text"])
        self.assertNotIn("Riched20", result["text"])
        self.assertNotIn("/p", result["text"])
        self.assertTrue(result["text"].startswith("Dear Hiring Committee,"))
        self.assertIn("This is", result["text"])
        self.assertIn("Second line", result["text"])

    def test_uses_gemini_for_image_ocr(self) -> None:
        captured = {}

        def fake_fetch(url: str, payload: dict) -> dict:
            captured["url"] = url
            captured["payload"] = payload
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Extracted image text"}
                            ]
                        }
                    }
                ]
            }

        service = OcrService(api_key="test-key", fetch_json=fake_fetch)
        result = service.extract_text(
            file_name="scan.png",
            mime_type="image/png",
            content_bytes=b"\x89PNG\r\n",
        )
        self.assertEqual(result["method"], "gemini_vision")
        self.assertEqual(result["text"], "Extracted image text")
        self.assertIn("inline_data", captured["payload"]["contents"][0]["parts"][1])

    def test_uses_filename_mime_when_uploaded_mime_is_octet_stream(self) -> None:
        captured = {}

        def fake_fetch(url: str, payload: dict) -> dict:
            captured["payload"] = payload
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Extracted PDF text"}
                            ]
                        }
                    }
                ]
            }

        service = OcrService(api_key="test-key", fetch_json=fake_fetch)
        result = service.extract_text(
            file_name="uploaded.pdf",
            mime_type="application/octet-stream",
            content_bytes=b"%PDF-1.5",
        )
        self.assertEqual(result["method"], "gemini_vision")
        self.assertEqual(result["mime_type"], "application/pdf")
        self.assertEqual(result["text"], "Extracted PDF text")
        self.assertEqual(captured["payload"]["contents"][0]["parts"][1]["inline_data"]["mime_type"], "application/pdf")


if __name__ == "__main__":
    unittest.main()
