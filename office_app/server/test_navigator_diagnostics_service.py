from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from office_app.server.navigator_diagnostics_service import NavigatorDiagnosticsService


class NavigatorDiagnosticsServiceTests(unittest.TestCase):
    def test_status_report_redacts_log_secrets_and_reports_recent_incidents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incident_log = root / "incident_log.csv"
            backend_log = root / "backend.out.log"
            frontend_log = root / "frontend.out.log"
            incident_log.write_text(
                "incident_id,utc_ts,severity,class,rule_or_gate,command,input_ref,output_ref,evidence_path,notes,state_sha256\n"
                "INC-1,2026-07-07T10:00:00Z,high,routing,gate,/request,input,output,evidence,Route failed,abc\n",
                encoding="utf-8",
            )
            backend_log.write_text("GOOGLE_OAUTH_CLIENT_SECRET=super-secret\nTraceback: bad route\n", encoding="utf-8")
            frontend_log.write_text("frontend ok\n", encoding="utf-8")
            service = NavigatorDiagnosticsService(
                health_provider=lambda: {"ok": True, "ts": "2026-07-07T10:01:00Z"},
                tool_names_provider=lambda: ["office.state_get", "office.navigator_status_report"],
                state_provider=lambda workspace_id: {"active_room": "lobby", "active_persona": "Receptionist"},
                incident_log_path=incident_log,
                backend_log_path=backend_log,
                frontend_log_path=frontend_log,
                env_getter=lambda name: "configured" if name == "SERPAPI_API_KEY" else "",
                utc_now=lambda: "2026-07-07T10:02:00Z",
            )

            report = service.status_report("ws1", session_id="sess1")

        self.assertTrue(report["health"]["ok"])
        self.assertEqual(report["workspace"]["active_room"], "lobby")
        self.assertTrue(report["config"]["serpapi_ready"])
        self.assertEqual(report["incidents"][0]["incident_id"], "INC-1")
        self.assertIn("[REDACTED]", "\n".join(report["logs"]["backend"]))
        self.assertNotIn("super-secret", "\n".join(report["logs"]["backend"]))

    def test_recent_errors_handles_missing_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = NavigatorDiagnosticsService(
                health_provider=lambda: {"ok": True},
                tool_names_provider=lambda: [],
                state_provider=lambda workspace_id: {},
                incident_log_path=root / "missing.csv",
                backend_log_path=root / "missing-backend.log",
                frontend_log_path=root / "missing-frontend.log",
                env_getter=lambda name: "",
                utc_now=lambda: "2026-07-07T10:02:00Z",
            )

            result = service.recent_errors("ws1")

        self.assertEqual(result["incidents"], [])
        self.assertEqual(result["logs"]["backend"], [])
        self.assertEqual(result["logs"]["frontend"], [])

    def test_explain_error_returns_actionable_navigator_text(self) -> None:
        service = NavigatorDiagnosticsService(
            health_provider=lambda: {"ok": True},
            tool_names_provider=lambda: [],
            state_provider=lambda workspace_id: {},
            incident_log_path=Path("missing.csv"),
            backend_log_path=Path("missing-backend.log"),
            frontend_log_path=Path("missing-frontend.log"),
            env_getter=lambda name: "",
            utc_now=lambda: "2026-07-07T10:02:00Z",
        )

        result = service.explain_error("ws1", error_text="Tool office.gmail_read is not allowed from room lobby.")

        self.assertEqual(result["category"], "capability_policy")
        self.assertIn("room capability", result["summary"].lower())
        self.assertIn("move to the correct room", result["next_step"].lower())

    def test_run_check_executes_only_allowlisted_check_and_redacts_output(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_runner(*, argv, cwd, timeout_seconds):
            calls.append({"argv": argv, "cwd": cwd, "timeout_seconds": timeout_seconds})
            return SimpleNamespace(
                returncode=0,
                stdout="line 1\nAPI_KEY=super-secret\nSMOKE TEST PASSED\n",
                stderr="",
            )

        service = NavigatorDiagnosticsService(
            health_provider=lambda: {"ok": True},
            tool_names_provider=lambda: [],
            state_provider=lambda workspace_id: {},
            incident_log_path=Path("missing.csv"),
            backend_log_path=Path("missing-backend.log"),
            frontend_log_path=Path("missing-frontend.log"),
            env_getter=lambda name: "",
            utc_now=lambda: "2026-07-07T10:02:00Z",
            command_runner=fake_runner,
        )

        result = service.run_check("ws1", check_name="standard_smoke", session_id="sess1")

        self.assertEqual(result["check_name"], "standard_smoke")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["session_id"], "sess1")
        self.assertIn("SMOKE TEST PASSED", "\n".join(result["stdout_tail"]))
        self.assertIn("[REDACTED]", "\n".join(result["stdout_tail"]))
        self.assertNotIn("super-secret", "\n".join(result["stdout_tail"]))
        self.assertIn("smoke_test.ps1", " ".join(calls[0]["argv"]))

    def test_run_check_rejects_unlisted_check_name(self) -> None:
        service = NavigatorDiagnosticsService(
            health_provider=lambda: {"ok": True},
            tool_names_provider=lambda: [],
            state_provider=lambda workspace_id: {},
            incident_log_path=Path("missing.csv"),
            backend_log_path=Path("missing-backend.log"),
            frontend_log_path=Path("missing-frontend.log"),
            env_getter=lambda name: "",
            utc_now=lambda: "2026-07-07T10:02:00Z",
            command_runner=lambda **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )

        result = service.run_check("ws1", check_name="powershell arbitrary command")

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["check_name"], "powershell arbitrary command")
        self.assertIn("not allowlisted", result["summary"])


if __name__ == "__main__":
    unittest.main()
