from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from office_app.server.handlers.image_handlers import build_image_handlers
from office_app.server.image_generation_service import ImageGenerationService
from office_app.server.request_pipeline import RequestPipeline


class ImageGenerationServiceTests(unittest.TestCase):
    def test_generate_image_uses_gemini_interactions_api(self) -> None:
        captured = {}
        image_payload = base64.b64encode(b"png-bytes").decode("ascii")

        def fake_fetch_json(url, headers, payload):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = payload
            return {"output_image": {"data": image_payload, "mime_type": "image/png"}}

        service = ImageGenerationService(env={"GEMINI_API_KEY": "test-key"}, fetch_json=fake_fetch_json)
        result = service.generate_image(prompt="Create a neon diner poster")

        self.assertEqual(captured["url"], "https://generativelanguage.googleapis.com/v1beta/interactions")
        self.assertEqual(captured["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(captured["payload"]["model"], "gemini-3.1-flash-image")
        self.assertEqual(captured["payload"]["input"][0]["text"], "Create a neon diner poster")
        self.assertEqual(result["content_base64"], image_payload)
        self.assertEqual(result["mime_type"], "image/png")

    def test_generate_image_requires_api_key(self) -> None:
        service = ImageGenerationService(env={})
        with self.assertRaises(HTTPException) as raised:
            service.generate_image(prompt="Create a poster")
        self.assertEqual(raised.exception.status_code, 503)


class ImageHandlerTests(unittest.TestCase):
    def test_handler_saves_generated_image_to_art_department_room_scope(self) -> None:
        generated = {
            "filename": "neon_diner.png",
            "content_base64": base64.b64encode(b"png-bytes").decode("ascii"),
            "mime_type": "image/png",
            "model": "gemini-3.1-flash-image",
        }
        image_service = SimpleNamespace(generate_image=lambda prompt, model=None: generated)
        kernel = SimpleNamespace(get_state=lambda workspace_id: {"active_room": "art_department", "active_persona": "Creative Director"})
        saved = {}

        def fake_upload_file(**kwargs):
            saved.update(kwargs)
            return {
                "file_id": "file_image",
                "original_name": kwargs["original_name"],
                "mime_type": kwargs["mime_type"],
                "kind": kwargs["kind"],
                "download_url": "/files/file_image/download?workspace_id=ws_test&scope=room",
            }

        deps = SimpleNamespace(
            resolve_workspace_id=lambda tool, args: args["workspace_id"],
            error_missing_required_field=lambda field: ValueError(field),
            image_generation_service=image_service,
            workspace_file_service=SimpleNamespace(upload_file=fake_upload_file),
            kernel=kernel,
        )
        handler = build_image_handlers(deps)["office.image_generate"]
        response = handler({"workspace_id": "ws_test", "session_id": "session_test", "prompt": "Create a neon diner poster"})

        self.assertEqual(saved["scope"], "room")
        self.assertEqual(saved["scope_ref"], "art_department")
        self.assertEqual(saved["kind"], "generated_image")
        self.assertEqual(response["structuredContent"]["file"]["file_id"], "file_image")


class ImageRoutingTests(unittest.TestCase):
    def test_art_department_image_request_routes_to_image_generate_tool(self) -> None:
        kernel = SimpleNamespace(get_state=lambda workspace_id: {"active_room": "art_department"})
        pipeline = RequestPipeline(
            kernel=kernel,
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-06-29T00:00:00Z",
            governance_registry_service=SimpleNamespace(),
        )
        route = pipeline.route_image_generation_request("ws_test", "generate an image of a neon diner poster")

        self.assertIsNotNone(route)
        assert route is not None
        self.assertEqual(route["tool"], "office.image_generate")
        self.assertEqual(route["capability"], "image.generate")

    def test_non_art_room_image_request_does_not_route(self) -> None:
        kernel = SimpleNamespace(get_state=lambda workspace_id: {"active_room": "marketing_room"})
        pipeline = RequestPipeline(
            kernel=kernel,
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-06-29T00:00:00Z",
            governance_registry_service=SimpleNamespace(),
        )

        self.assertIsNone(pipeline.route_image_generation_request("ws_test", "generate an image of a neon diner poster"))


if __name__ == "__main__":
    unittest.main()
