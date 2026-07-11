import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1]/"skills/_shared/agent_slot_ledger.py"


class SlotTests(unittest.TestCase):
    def command(self, *args, ok=True):
        result = subprocess.run(["python3", str(SCRIPT), *args], capture_output=True, text=True)
        if ok: self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_close_before_release(self):
        with tempfile.TemporaryDirectory() as raw:
            ledger = str(Path(raw)/"ledger.json")
            self.command("init", ledger); self.command("acquire", ledger, "--label", "review")
            self.command("bind-agent", ledger, "--label", "review", "--agent-id", "a1")
            self.assertNotEqual(self.command("release", ledger, "--agent-id", "a1", ok=False).returncode, 0)
            self.command("mark-completed", ledger, "--agent-id", "a1")
            self.command("mark-closed", ledger, "--agent-id", "a1", "--close-evidence", "completed")
            self.command("release", ledger, "--agent-id", "a1")
            self.assertEqual(json.loads(Path(ledger).read_text())["slots"][0]["state"], "released")

    def test_reap_refuses_live_and_compact_requires_zero(self):
        with tempfile.TemporaryDirectory() as raw:
            ledger=str(Path(raw)/"ledger.json"); self.command("init",ledger); self.command("acquire",ledger,"--label","live")
            self.command("reap",ledger)
            self.assertEqual(json.loads(Path(ledger).read_text())["slots"][0]["state"],"reserved")
            self.assertNotEqual(self.command("compact",ledger,ok=False).returncode,0)

    def test_nonempty_legacy_is_blocked(self):
        with tempfile.TemporaryDirectory() as raw:
            ledger=Path(raw)/"ledger.json"; ledger.write_text(json.dumps({"max":1,"slots":[{"label":"unknown"}]}))
            self.assertNotEqual(self.command("status",str(ledger),ok=False).returncode,0)


if __name__ == "__main__": unittest.main()
