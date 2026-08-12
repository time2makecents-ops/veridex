from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from office_app.server import app as app_module


class SingleUserModeTests(unittest.TestCase):
    def test_single_user_endpoint_restores_stable_account_session(self) -> None:
        service = Mock()
        service.enter_lobby.return_value = {
            "user": {"user_id": "usr_local", "display_name": "Admin"},
            "workspace_id": "ws_1",
            "session_id": "sess_1",
        }
        with patch.object(app_module, "VERIDEX_SINGLE_USER_MODE", True), patch.object(app_module, "user_service", service):
            response = app_module.lobby_single_user()

        service.ensure_admin_user.assert_called_once_with()
        service.enter_lobby.assert_called_once_with(pin_code="1978")
        self.assertEqual(response["structuredContent"]["session_id"], "sess_1")
        self.assertIn("Session restored: sess_1", response["content"][0]["text"])

    def test_single_user_endpoint_is_unavailable_when_disabled(self) -> None:
        with patch.object(app_module, "VERIDEX_SINGLE_USER_MODE", False):
            with self.assertRaises(HTTPException) as raised:
                app_module.lobby_single_user()
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
