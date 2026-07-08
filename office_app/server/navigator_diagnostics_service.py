from __future__ import annotations

import csv
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence


HealthProvider = Callable[[], Dict[str, Any]]
ToolNamesProvider = Callable[[], List[str]]
StateProvider = Callable[[str], Dict[str, Any]]
EnvGetter = Callable[[str], str]
UtcNow = Callable[[], str]
CommandRunner = Callable[..., Any]


@dataclass(frozen=True)
class NavigatorCheckSpec:
    name: str
    label: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "office_app" / "frontend"


NAVIGATOR_CHECKS: Dict[str, NavigatorCheckSpec] = {
    "standard_smoke": NavigatorCheckSpec(
        name="standard_smoke",
        label="Standard smoke test",
        argv=(
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "office_app" / "smoke_test.ps1"),
        ),
        cwd=PROJECT_ROOT,
        timeout_seconds=120,
    ),
    "work_context_smoke": NavigatorCheckSpec(
        name="work_context_smoke",
        label="Work context smoke test",
        argv=(
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "office_app" / "work_context_smoke.ps1"),
        ),
        cwd=PROJECT_ROOT,
        timeout_seconds=180,
    ),
    "backend_tests": NavigatorCheckSpec(
        name="backend_tests",
        label="Backend unit tests",
        argv=("python", "-m", "unittest", "discover", "-s", "office_app/server", "-p", "test_*.py"),
        cwd=PROJECT_ROOT,
        timeout_seconds=180,
    ),
    "frontend_build": NavigatorCheckSpec(
        name="frontend_build",
        label="Frontend production build",
        argv=("npm.cmd", "run", "build"),
        cwd=FRONTEND_ROOT,
        timeout_seconds=180,
    ),
}


SECRET_LINE_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL)[A-Z0-9_]*)\s*=\s*([^ \r\n]+)"
)


class NavigatorDiagnosticsService:
    def __init__(
        self,
        *,
        health_provider: HealthProvider,
        tool_names_provider: ToolNamesProvider,
        state_provider: StateProvider,
        incident_log_path: Path,
        backend_log_path: Path,
        frontend_log_path: Path,
        env_getter: EnvGetter,
        utc_now: UtcNow,
        command_runner: Optional[CommandRunner] = None,
    ) -> None:
        self.health_provider = health_provider
        self.tool_names_provider = tool_names_provider
        self.state_provider = state_provider
        self.incident_log_path = incident_log_path
        self.backend_log_path = backend_log_path
        self.frontend_log_path = frontend_log_path
        self.env_getter = env_getter
        self.utc_now = utc_now
        self.command_runner = command_runner or self._run_command

    @staticmethod
    def _redact(value: str) -> str:
        return SECRET_LINE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)

    def _tail_lines(self, path: Path, *, limit: int = 40) -> List[str]:
        if not path.exists() or not path.is_file():
            return []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return [self._redact(line) for line in lines[-limit:]]

    @staticmethod
    def _run_command(*, argv: Sequence[str], cwd: Path, timeout_seconds: int) -> Any:
        return subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )

    def _tail_text(self, text: str, *, limit: int = 40) -> List[str]:
        lines = str(text or "").splitlines()
        return [self._redact(line) for line in lines[-limit:]]

    def _recent_incidents(self, *, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.incident_log_path.exists() or not self.incident_log_path.is_file():
            return []
        try:
            with self.incident_log_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        except OSError:
            return []
        cleaned: List[Dict[str, Any]] = []
        for row in rows[-limit:]:
            cleaned.append(
                {
                    "incident_id": str(row.get("incident_id") or "").strip(),
                    "utc_ts": str(row.get("utc_ts") or "").strip(),
                    "severity": str(row.get("severity") or "").strip(),
                    "class": str(row.get("class") or "").strip(),
                    "rule_or_gate": str(row.get("rule_or_gate") or "").strip(),
                    "command": str(row.get("command") or "").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                }
            )
        return cleaned

    def _safe_state(self, workspace_id: str) -> Dict[str, Any]:
        if not workspace_id:
            return {}
        try:
            state = self.state_provider(workspace_id)
        except Exception as exc:
            return {"error": str(exc)}
        return {
            "active_room": str(state.get("active_room") or "").strip(),
            "active_persona": str(state.get("active_persona") or "").strip(),
        }

    def _config_readiness(self) -> Dict[str, bool]:
        google_search_ready = bool(
            (self.env_getter("GOOGLE_SEARCH_API_KEY") or self.env_getter("GEMINI_API_KEY"))
            and (self.env_getter("GOOGLE_SEARCH_ENGINE_ID") or self.env_getter("GOOGLE_CSE_ID"))
        )
        return {
            "serpapi_ready": bool(self.env_getter("SERPAPI_API_KEY")),
            "google_custom_search_ready": google_search_ready,
            "duckduckgo_fallback": True,
            "google_oauth_configured": bool(
                self.env_getter("GOOGLE_OAUTH_CLIENT_ID")
                and self.env_getter("GOOGLE_OAUTH_CLIENT_SECRET")
                and self.env_getter("GOOGLE_OAUTH_REDIRECT_URI")
                and self.env_getter("VERIDEX_INTEGRATION_ENCRYPTION_KEY")
            ),
        }

    @staticmethod
    def _recommendation(
        *,
        action_id: str,
        label: str,
        kind: str,
        reason: str,
        check_name: str = "",
    ) -> Dict[str, Any]:
        recommendation: Dict[str, Any] = {
            "action_id": action_id,
            "label": label,
            "kind": kind,
            "requires_confirmation": True,
            "reason": reason,
        }
        if check_name:
            recommendation["check_name"] = check_name
        return recommendation

    def status_report(self, workspace_id: str, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        tool_names = self.tool_names_provider()
        expected_tools = {
            "office.state_get",
            "office.room_set",
            "office.navigator_status_report",
            "office.navigator_recent_errors",
            "office.navigator_explain_error",
            "office.navigator_run_check",
        }
        return {
            "generated_utc": self.utc_now(),
            "workspace_id": workspace_id,
            "session_id": session_id or "",
            "health": self.health_provider(),
            "workspace": self._safe_state(workspace_id),
            "tools": {
                "count": len(tool_names),
                "missing_expected": sorted(expected_tools.difference(tool_names)),
            },
            "config": self._config_readiness(),
            "incidents": self._recent_incidents(limit=10),
            "logs": {
                "backend": self._tail_lines(self.backend_log_path, limit=40),
                "frontend": self._tail_lines(self.frontend_log_path, limit=40),
            },
        }

    def recent_errors(self, workspace_id: str, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "generated_utc": self.utc_now(),
            "workspace_id": workspace_id,
            "session_id": session_id or "",
            "incidents": self._recent_incidents(limit=10),
            "logs": {
                "backend": self._tail_lines(self.backend_log_path, limit=40),
                "frontend": self._tail_lines(self.frontend_log_path, limit=40),
            },
        }

    def explain_error(self, workspace_id: str, *, error_text: str = "", session_id: Optional[str] = None) -> Dict[str, Any]:
        text = re.sub(r"\s+", " ", str(error_text or "").strip())
        lowered = text.lower()
        category = "unknown"
        summary = "I need the exact error text or a recent failed action to diagnose this cleanly."
        next_step = "Run a Navigator status report, then retry the action and give me the exact failure text."
        recommendations = [
            self._recommendation(
                action_id="run_status_report",
                label="Run Navigator status report",
                kind="status_report",
                reason="A status report checks health, tool registration, active room/persona, config readiness, incidents, and log tails.",
            )
        ]

        if "not allowed from room" in lowered or "capability profile" in lowered:
            category = "capability_policy"
            summary = "The action was blocked by a room capability policy."
            next_step = "Move to the correct room or use the assistant that owns that capability, then retry."
            recommendations = [
                self._recommendation(
                    action_id="move_to_room",
                    label="Move to the correct room",
                    kind="guidance",
                    reason="Capability policies are room-scoped.",
                )
            ]
        elif "google is not connected" in lowered or "connect it from profile" in lowered:
            category = "google_connection"
            summary = "The Google integration is not connected for the current user/session."
            next_step = "Open Profile, connect Google, then retry the Gmail or Calendar action."
            recommendations = [
                self._recommendation(
                    action_id="open_profile",
                    label="Open Profile and connect Google",
                    kind="guidance",
                    reason="Google actions require a connected account before Veridex can prepare Gmail or Calendar work.",
                )
            ]
        elif "not listening" in lowered or "connection refused" in lowered or "networkerror" in lowered:
            category = "runtime_connection"
            summary = "A local backend or frontend connection failed."
            next_step = "Restart Veridex and run the standard smoke test before retrying."
            recommendations = [
                self._recommendation(
                    action_id="run_standard_smoke",
                    label="Run standard smoke test",
                    kind="run_check",
                    check_name="standard_smoke",
                    reason="The standard smoke test verifies the backend, frontend, tool registry, and search-provider readiness.",
                )
            ]
        elif text:
            summary = f"I can see the failure text, but it does not match a known diagnostic category: {text}"
            next_step = "Run recent errors and a status report so I can compare it with logs and incidents."
            recommendations = [
                self._recommendation(
                    action_id="run_recent_errors",
                    label="Run recent errors",
                    kind="recent_errors",
                    reason="Recent errors show incident rows and redacted backend/frontend log tails.",
                ),
                self._recommendation(
                    action_id="run_status_report",
                    label="Run Navigator status report",
                    kind="status_report",
                    reason="A status report adds health, tool, active room/persona, and config context.",
                ),
            ]

        return {
            "generated_utc": self.utc_now(),
            "workspace_id": workspace_id,
            "session_id": session_id or "",
            "category": category,
            "summary": summary,
            "next_step": next_step,
            "recommendations": recommendations,
            "error_text": self._redact(text),
        }

    def run_check(self, workspace_id: str, *, check_name: str = "", session_id: Optional[str] = None) -> Dict[str, Any]:
        normalized = re.sub(r"[^a-z0-9_]+", "_", str(check_name or "").strip().lower()).strip("_")
        spec = NAVIGATOR_CHECKS.get(normalized)
        if spec is None:
            return {
                "generated_utc": self.utc_now(),
                "workspace_id": workspace_id,
                "session_id": session_id or "",
                "check_name": str(check_name or ""),
                "status": "rejected",
                "exit_code": None,
                "duration_seconds": 0.0,
                "stdout_tail": [],
                "stderr_tail": [],
                "summary": f"Navigator check '{check_name}' is not allowlisted.",
                "allowed_checks": sorted(NAVIGATOR_CHECKS),
            }

        started = time.monotonic()
        try:
            completed = self.command_runner(argv=spec.argv, cwd=spec.cwd, timeout_seconds=spec.timeout_seconds)
            duration = round(time.monotonic() - started, 3)
            exit_code = int(getattr(completed, "returncode", 1))
            status = "passed" if exit_code == 0 else "failed"
            stdout_tail = self._tail_text(str(getattr(completed, "stdout", "") or ""), limit=40)
            stderr_tail = self._tail_text(str(getattr(completed, "stderr", "") or ""), limit=40)
        except subprocess.TimeoutExpired as exc:
            duration = round(time.monotonic() - started, 3)
            exit_code = None
            status = "timed_out"
            stdout_tail = self._tail_text(str(exc.stdout or ""), limit=40)
            stderr_tail = self._tail_text(str(exc.stderr or ""), limit=40)
        except OSError as exc:
            duration = round(time.monotonic() - started, 3)
            exit_code = None
            status = "failed"
            stdout_tail = []
            stderr_tail = [self._redact(str(exc))]

        return {
            "generated_utc": self.utc_now(),
            "workspace_id": workspace_id,
            "session_id": session_id or "",
            "check_name": spec.name,
            "label": spec.label,
            "status": status,
            "exit_code": exit_code,
            "duration_seconds": duration,
            "timeout_seconds": spec.timeout_seconds,
            "command_display": " ".join(spec.argv),
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "summary": f"Navigator check {spec.name} {status}.",
            "allowed_checks": sorted(NAVIGATOR_CHECKS),
        }
