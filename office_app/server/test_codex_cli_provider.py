from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from office_app.server.providers.codex_cli_provider import CodexCliProvider


class CodexCliProviderTests(unittest.TestCase):
    def test_forwards_task_type_and_returns_dynamic_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            gateway = Path(temp_dir) / "gateway.py"
            gateway.touch()
            provider = CodexCliProvider(gateway_path=str(gateway), python_command=os.sys.executable)
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "provider": "codex_cli",
                        "model": "gpt-5.6-sol",
                        "task_type": "coding",
                        "text": "Implemented.",
                    }
                ),
                stderr="",
            )
            with patch("office_app.server.providers.codex_cli_provider.shutil.which", return_value=r"C:\codex.cmd"):
                with patch("office_app.server.providers.codex_cli_provider.subprocess.run", return_value=completed) as run:
                    result = provider.generate_response(
                        system_prompt="system",
                        user_prompt="fix the code",
                        context={"workspace_id": "ws"},
                        settings={"_task_type": "coding"},
                    )
            payload = json.loads(run.call_args.kwargs["input"])
            self.assertEqual(payload["task_type"], "coding")
            self.assertEqual(result.provider, "codex_cli")
            self.assertEqual(result.model, "gpt-5.6-sol")
            self.assertEqual(result.text, "Implemented.")


if __name__ == "__main__":
    unittest.main()
