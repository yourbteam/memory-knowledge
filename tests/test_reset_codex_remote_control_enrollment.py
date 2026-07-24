import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT = str(
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "reset_codex_remote_control_enrollment.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("reset_remote_regression", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_fixture(root: Path, module):
    codex_home = root / ".codex"
    (codex_home / "sqlite").mkdir(parents=True)
    installation = "captured-new-installation-id"
    (codex_home / "installation_id").write_text(installation)
    state = {
        module.INSTALLATION_KEY: installation,
        module.ENVIRONMENT_KEY: "captured-cloned-environment",
        "unrelated": {"keep": True},
    }
    for path in module._global_state_paths(codex_home):
        path.write_text(json.dumps(state))
    for path in module._database_paths(codex_home):
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE remote_control_enrollments ("
                "websocket_url TEXT NOT NULL, account_id TEXT NOT NULL, "
                "app_server_client_name TEXT NOT NULL, server_id TEXT NOT NULL, "
                "environment_id TEXT NOT NULL, server_name TEXT NOT NULL, "
                "updated_at INTEGER NOT NULL)"
            )
            conn.execute(
                "INSERT INTO remote_control_enrollments VALUES (?,?,?,?,?,?,?)",
                ("wss://example", "acct", "Codex Desktop", "server", "env", "old-host", 1),
            )
            conn.commit()
        finally:
            conn.close()
    return codex_home


class ResetLoopRegressionTests(unittest.TestCase):
    def setUp(self):
        self._warning_context = warnings.catch_warnings()
        self._warning_context.__enter__()
        warnings.simplefilter("error", ResourceWarning)

    def tearDown(self):
        self._warning_context.__exit__(None, None, None)

    def test_missing_receipt_is_created_and_same_receipt_is_at_most_once(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            codex_home = create_fixture(root, module)
            backups = root / "backups"
            receipt = root / "receipts" / "reset.json"
            argv = [
                SCRIPT,
                "reset",
                "--codex-home",
                str(codex_home),
                "--backup-root",
                str(backups),
                "--receipt",
                str(receipt),
            ]
            with patch.object(module, "_app_running", return_value=False), patch.object(
                sys, "argv", argv
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                first = module.main()
            self.assertEqual(first, 0)
            self.assertTrue(receipt.is_file())
            self.assertEqual(json.loads(receipt.read_text())["status"], "complete")
            self.assertEqual(len(list(backups.glob("remote-control-enrollment-reset-*"))), 1)

            with patch.object(module, "_app_running", return_value=False), patch.object(
                sys, "argv", argv
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                second = module.main()
            self.assertEqual(second, 0)
            self.assertEqual(len(list(backups.glob("remote-control-enrollment-reset-*"))), 1)
            self.assertEqual(json.loads(receipt.read_text())["status"], "complete")

    def test_schedule_detaches_once_and_reuses_schedule_marker(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            codex_home = create_fixture(root, module)
            receipt = root / "receipts" / "scheduled-reset.json"
            command = [
                sys.executable,
                SCRIPT,
                "schedule",
                "--codex-home",
                str(codex_home),
                "--backup-root",
                str(root / "backups"),
                "--wait-for-app-exit",
                "0",
                "--receipt",
                str(receipt),
            ]
            first = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertEqual(first_payload["status"], "scheduled")

            deadline = time.monotonic() + 5
            receipt_payload = None
            while time.monotonic() < deadline:
                if receipt.is_file():
                    receipt_payload = json.loads(receipt.read_text())
                    if receipt_payload.get("status") in {"complete", "failed"}:
                        break
                time.sleep(0.05)
            else:
                current = receipt.read_text() if receipt.is_file() else "<missing>"
                self.fail(f"receipt did not reach a terminal state: {current}")
            self.assertIn(receipt_payload["status"], {"complete", "failed"})

            second = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(second.stdout)["status"], "already_attempted")
            self.assertTrue(Path(f"{receipt}.scheduled").is_file())


if __name__ == "__main__":
    unittest.main()
