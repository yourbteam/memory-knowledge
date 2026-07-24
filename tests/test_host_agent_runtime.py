"""Focused tests for the host-neutral bounded assessment runtime."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
MODULE = REPO / "skills" / "_shared" / "host_agent_runtime.py"
LEDGER = REPO / "skills" / "_shared" / "agent_slot_ledger.py"

spec = importlib.util.spec_from_file_location("host_agent_runtime", MODULE)
har = importlib.util.module_from_spec(spec)
sys.modules["host_agent_runtime"] = har
spec.loader.exec_module(har)

SCHEMA = {"type": "object", "required": ["verdict"], "properties": {"verdict": {"type": "string"}}}

CLAUDE_HELP = " ".join(har.CLAUDE_REQUIRED_FLAGS)
CODEX_HELP = " ".join(har.CODEX_REQUIRED_FLAGS)


def fake_executable(base: Path, name: str, help_text: str, body: str) -> Path:
    """A fake host CLI: --help/--version answer the probe; anything else runs `body`."""
    path = base / name
    path.write_text(
        "#!/bin/sh\n"
        "for arg in \"$@\"; do\n"
        "  if [ \"$arg\" = \"--help\" ]; then printf '%s' \"" + help_text + "\"; exit 0; fi\n"
        "  if [ \"$arg\" = \"--version\" ]; then echo fake-1.0.0; exit 0; fi\n"
        "done\n" + body + "\n"
    )
    path.chmod(0o755)
    return path


def make_request(base: Path, host: str, executable: Path, **overrides) -> "har.HostAgentRequest":
    prompt = base / "prompt.md"
    if not prompt.exists():
        prompt.write_text("Assess the fixture and answer.")
    values = dict(
        schema_version=1, host=host, executable=str(executable), role="research-assessor",
        prompt_path=prompt, working_directory=base, allowed_read_roots=(base,),
        allowed_tools=("Read",), disallowed_tools=("Edit", "Write", "Bash"),
        timeout_seconds=10, max_turns=3, max_budget_usd=Decimal("0.25"),
        output_schema=SCHEMA, slot_id="", attempt_id="attempt-1",
    )
    values.update(overrides)
    return har.HostAgentRequest(**values)


class LedgerHarness:
    def __init__(self, base: Path):
        self.path = base / "ledger.json"
        self._run("init", str(self.path), "--max", "1")

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(LEDGER), *args], capture_output=True, text=True)

    def acquire(self, label: str) -> str:
        completed = self._run("acquire", str(self.path), "--label", label)
        assert completed.returncode == 0, completed.stderr
        return completed.stdout.split()[1]

    def status(self) -> dict:
        completed = self._run("status", str(self.path), "--json")
        payload = json.loads(completed.stdout)
        payload["active"] = sum(1 for slot in payload["slots"] if slot["state"] != "released")
        return payload


class ProbeTests(unittest.TestCase):
    def test_probe_reports_missing_flags_and_unavailable(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            exe = fake_executable(base, "claude", "--print --output-format", "exit 0")
            capabilities = har.probe_host(str(exe), "claude")
            self.assertFalse(capabilities.available)
            self.assertIn("--json-schema", capabilities.missing_required_flags)
            self.assertEqual(len(capabilities.help_sha256), 64)

    def test_probe_full_help_is_available(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            exe = fake_executable(base, "claude", CLAUDE_HELP, "exit 0")
            capabilities = har.probe_host(str(exe), "claude")
            self.assertTrue(capabilities.available)
            self.assertEqual(capabilities.missing_required_flags, ())
            self.assertEqual(capabilities.version, "fake-1.0.0")


class RunAssessmentTests(unittest.TestCase):
    def _claude_success_body(self) -> str:
        envelope = {"type": "result", "subtype": "success", "is_error": False,
                    "session_id": "sess-123", "result": json.dumps({"verdict": "pass"})}
        return "cat >/dev/null\nprintf '%s' '" + json.dumps(envelope) + "'\nexit 0"

    def test_capability_missing_never_touches_ledger(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            exe = fake_executable(base, "claude", "no flags here", "exit 0")
            request = make_request(base, "claude", exe, slot_id="slot-unused")
            outcome = har.run_assessment(request, ledger.path)
            self.assertEqual(outcome.status, "CAPABILITY_MISSING")
            self.assertIsNone(outcome.exit_code)
            self.assertFalse(outcome.slot_released)
            self.assertEqual(outcome.completion_evidence,
                             har.CompletionEvidence(False, False, False, False, False))
            self.assertEqual(ledger.status()["active"], 0)

    def test_claude_success_releases_slot_and_validates_output(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            exe = fake_executable(base, "claude", CLAUDE_HELP, self._claude_success_body())
            slot = ledger.acquire("research")
            request = make_request(base, "claude", exe, slot_id=slot)
            outcome = har.run_assessment(request, ledger.path)
            self.assertEqual(outcome.status, "SUCCEEDED", outcome.diagnostic_code)
            self.assertEqual(outcome.output, {"verdict": "pass"})
            self.assertEqual(outcome.session_id, "sess-123")
            self.assertEqual(outcome.runtime_agent_id, "sess-123")
            self.assertIsNotNone(outcome.output_sha256)
            self.assertIsNone(outcome.diagnostic_code)
            self.assertTrue(outcome.slot_released)
            self.assertEqual(outcome.completion_evidence,
                             har.CompletionEvidence(True, True, True, True, True))
            self.assertEqual(ledger.status()["active"], 0)

    def test_nonzero_exit_is_failed_with_slot_released(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            exe = fake_executable(base, "claude", CLAUDE_HELP, "cat >/dev/null\nexit 3")
            slot = ledger.acquire("research")
            outcome = har.run_assessment(make_request(base, "claude", exe, slot_id=slot), ledger.path)
            self.assertEqual(outcome.status, "FAILED")
            self.assertEqual(outcome.exit_code, 3)
            self.assertEqual(outcome.diagnostic_code, "exit:3")
            self.assertIsNone(outcome.output)
            self.assertTrue(outcome.slot_released)
            self.assertFalse(outcome.completion_evidence.ledger_completed)
            self.assertTrue(outcome.completion_evidence.ledger_closed)
            self.assertEqual(ledger.status()["active"], 0)

    def test_zero_exit_with_schema_invalid_output_is_invalid_output(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            envelope = {"type": "result", "is_error": False, "session_id": "sess-9",
                        "result": json.dumps({"wrong": True})}
            body = "cat >/dev/null\nprintf '%s' '" + json.dumps(envelope) + "'\nexit 0"
            exe = fake_executable(base, "claude", CLAUDE_HELP, body)
            slot = ledger.acquire("research")
            outcome = har.run_assessment(make_request(base, "claude", exe, slot_id=slot), ledger.path)
            self.assertEqual(outcome.status, "INVALID_OUTPUT")
            self.assertIsNone(outcome.output)
            self.assertTrue(outcome.slot_released)
            self.assertEqual(ledger.status()["active"], 0)

    def test_timeout_is_timed_out_and_releases_slot(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            exe = fake_executable(base, "claude", CLAUDE_HELP, "cat >/dev/null\nsleep 30")
            slot = ledger.acquire("research")
            request = make_request(base, "claude", exe, slot_id=slot, timeout_seconds=1)
            outcome = har.run_assessment(request, ledger.path)
            self.assertEqual(outcome.status, "TIMED_OUT")
            self.assertFalse(outcome.completion_evidence.process_terminal)
            self.assertIsNone(outcome.exit_code)
            self.assertTrue(outcome.slot_released)
            self.assertEqual(ledger.status()["active"], 0)

    def test_codex_success_through_output_last_message(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            body = (
                "cat >/dev/null\nresult=''\nprev=''\n"
                "for arg in \"$@\"; do\n"
                "  if [ \"$prev\" = \"--output-last-message\" ]; then result=\"$arg\"; fi\n"
                "  prev=\"$arg\"\n"
                "done\n"
                "printf '%s' '" + json.dumps({"verdict": "pass"}) + "' > \"$result\"\nexit 0"
            )
            exe = fake_executable(base, "codex", CODEX_HELP, body)
            slot = ledger.acquire("research")
            outcome = har.run_assessment(make_request(base, "codex", exe, slot_id=slot), ledger.path)
            self.assertEqual(outcome.status, "SUCCEEDED", outcome.diagnostic_code)
            self.assertEqual(outcome.output, {"verdict": "pass"})
            self.assertTrue(outcome.completion_evidence.host_terminal)
            self.assertTrue(outcome.slot_released)
            self.assertEqual(ledger.status()["active"], 0)

    def test_ledger_failure_after_valid_output_is_ledger_error(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            exe = fake_executable(base, "claude", CLAUDE_HELP, self._claude_success_body())
            request = make_request(base, "claude", exe, slot_id="slot-that-does-not-exist")
            outcome = har.run_assessment(request, ledger.path)
            self.assertEqual(outcome.status, "LEDGER_ERROR")
            self.assertEqual(outcome.output, {"verdict": "pass"})
            self.assertFalse(outcome.slot_released)
            self.assertTrue(outcome.diagnostic_code.startswith("ledger-lifecycle:"))

    def test_request_validation_rejects_relative_paths_and_bad_bounds(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            exe = fake_executable(base, "claude", CLAUDE_HELP, "exit 0")
            request = make_request(base, "claude", exe, slot_id="s", timeout_seconds=0)
            with self.assertRaises(har.RequestError):
                har.run_assessment(request, base / "ledger.json")
            relative = make_request(base, "claude", exe, slot_id="s")
            relative = har.HostAgentRequest(**{**relative.__dict__, "executable": "claude"})
            with self.assertRaises(har.RequestError):
                har.run_assessment(relative, base / "ledger.json")

    def test_diagnostics_never_contain_prompt_or_output_text(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            ledger = LedgerHarness(base)
            secret = "SECRET-TOKEN-XYZ"
            prompt = base / "prompt.md"
            prompt.write_text(f"Contains {secret}")
            exe = fake_executable(base, "claude", CLAUDE_HELP, "cat >/dev/null\nexit 9")
            slot = ledger.acquire("research")
            outcome = har.run_assessment(make_request(base, "claude", exe, slot_id=slot), ledger.path)
            self.assertNotIn(secret, outcome.diagnostic_code or "")
            self.assertNotIn(secret, json.dumps(outcome.status))


class ArgvTests(unittest.TestCase):
    def test_claude_argv_is_bounded_and_shell_free(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            exe = fake_executable(base, "claude", CLAUDE_HELP, "exit 0")
            request = make_request(base, "claude", exe, slot_id="s")
            argv = har.build_argv(request, base / "schema.json", None)
            self.assertEqual(argv[0], str(exe))
            self.assertIn("--print", argv)
            self.assertNotIn("--max-turns", argv)  # not in the probed help; budget+timeout carry the bound
            capable = har.probe_host(str(fake_executable(base, "claude2", CLAUDE_HELP + " --max-turns", "exit 0")), "claude")
            self.assertIn("--max-turns", har.build_argv(request, base / "schema.json", None, capable))
            self.assertIn("--max-budget-usd", argv)
            self.assertIn("--no-session-persistence", argv)
            self.assertIn("--disallowedTools", argv)
            self.assertEqual(argv[argv.index("--disallowedTools") + 1], "Edit,Write,Bash")
            self.assertNotIn(";", " ".join(argv))

    def test_codex_argv_matches_locked_exec_shape(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            exe = fake_executable(base, "codex", CODEX_HELP, "exit 0")
            request = make_request(base, "codex", exe, slot_id="s")
            argv = har.build_argv(request, base / "schema.json", base / "result.json")
            self.assertEqual(argv[1], "exec")
            self.assertIn("--ephemeral", argv)
            self.assertIn("read-only", argv)
            self.assertEqual(argv[-1], "-")


if __name__ == "__main__":
    unittest.main()
