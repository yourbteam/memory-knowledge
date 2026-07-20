import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1]/"skills/_shared/agent_slot_ledger.py"
SPEC = importlib.util.spec_from_file_location("agent_slot_ledger", SCRIPT)
agent_slot_ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_slot_ledger)


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

    def test_slot_id_remains_unambiguous_when_label_is_reused(self):
        with tempfile.TemporaryDirectory() as raw:
            ledger = str(Path(raw) / "ledger.json")
            self.command("init", ledger)
            self.command("acquire", ledger, "--label", "research")
            self.command("bind-agent", ledger, "--slot-id", "s1", "--agent-id", "a1")
            self.command("mark-completed", ledger, "--slot-id", "s1")
            self.command("mark-closed", ledger, "--slot-id", "s1", "--close-evidence", "completed")
            self.command("release", ledger, "--slot-id", "s1")
            self.command("acquire", ledger, "--label", "research")
            self.command("bind-agent", ledger, "--slot-id", "s2", "--agent-id", "a2")
            slots = json.loads(Path(ledger).read_text())["slots"]
            self.assertEqual([(slot["id"], slot["state"]) for slot in slots], [
                ("s1", "released"), ("s2", "running"),
            ])

    def test_nonempty_legacy_is_blocked(self):
        with tempfile.TemporaryDirectory() as raw:
            ledger=Path(raw)/"ledger.json"; ledger.write_text(json.dumps({"max":1,"slots":[{"label":"unknown"}]}))
            self.assertNotEqual(self.command("status",str(ledger),ok=False).returncode,0)

    def test_abandon_runtime_id_is_unique_across_every_other_slot_state(self):
        states = ("reserved", "running", "completed", "closed", "abandoned", "released")
        for state in states:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as raw:
                ledger = Path(raw) / "ledger.json"
                ledger.write_text(json.dumps({
                    "version": 2,
                    "max": 3,
                    "slots": [
                        {
                            "id": "s1",
                            "label": "target",
                            "state": "reserved",
                            "agent_id": None,
                            "acquired_at": 1,
                            "evidence": {},
                        },
                        {
                            "id": "s2",
                            "label": "prior",
                            "state": state,
                            "agent_id": "duplicate-agent",
                            "acquired_at": 1,
                            "evidence": {},
                        },
                    ],
                }))
                result = self.command(
                    "abandon", str(ledger), "--slot-id", "s1",
                    "--reason", "bind failed",
                    "--runtime-agent-id", "duplicate-agent",
                    "--close-evidence", "closed",
                    ok=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(json.loads(ledger.read_text())["slots"][0]["state"], "reserved")

    def test_abandon_exact_same_slot_replay_is_idempotent_and_conflict_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            ledger = str(Path(raw) / "ledger.json")
            self.command("init", ledger, "--max", "2")
            self.command("acquire", ledger, "--label", "target")
            command = (
                "abandon", ledger, "--slot-id", "s1", "--reason", "bind failed",
                "--runtime-agent-id", "agent-1", "--close-evidence", "closed",
            )
            self.command(*command)
            before = Path(ledger).read_bytes()
            self.command(*command)
            self.assertEqual(Path(ledger).read_bytes(), before)
            conflict = self.command(
                "abandon", ledger, "--slot-id", "s1", "--reason", "different",
                "--runtime-agent-id", "agent-1", "--close-evidence", "closed",
                ok=False,
            )
            self.assertNotEqual(conflict.returncode, 0)

    def test_released_slot_projection_and_digest_are_exact(self):
        slot = {
            "id": "s7",
            "label": "requirements-coverage",
            "state": "released",
            "agent_id": "agent-7",
            "acquired_at": 10,
            "bound_at": 11,
            "completed_at": 12,
            "closed_at": 13,
            "released_at": 14,
            "evidence": {"close": "wait returned terminal", "abandon_reason": None},
            "consumer_private_field": "not part of the projection",
        }
        expected = {
            "id": "s7",
            "label": "requirements-coverage",
            "state": "released",
            "agent_id": "agent-7",
            "acquired_at": 10,
            "bound_at": 11,
            "completed_at": 12,
            "closed_at": 13,
            "abandoned_at": None,
            "released_at": 14,
            "evidence": {"close": "wait returned terminal", "abandon_reason": None},
        }
        canonical = json.dumps(
            expected, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")

        self.assertEqual(agent_slot_ledger.released_slot_projection(slot), expected)
        self.assertEqual(
            agent_slot_ledger.released_slot_close_evidence_sha256(slot),
            hashlib.sha256(canonical).hexdigest(),
        )

    def test_released_slot_projection_normalizes_absent_values(self):
        slot = {"id": "s1", "label": "spawn", "state": "released"}
        projection = agent_slot_ledger.released_slot_projection(slot)
        self.assertIsNone(projection["agent_id"])
        timestamps = (
            "acquired_at", "bound_at", "completed_at", "closed_at",
            "abandoned_at", "released_at",
        )
        self.assertTrue(all(projection[field] is None for field in timestamps))
        self.assertEqual(projection["evidence"], {"close": None, "abandon_reason": None})

    def test_released_slot_projection_rejects_malformed_slots(self):
        valid = {
            "id": "s1",
            "label": "review",
            "state": "released",
            "agent_id": None,
            "released_at": 2,
            "evidence": {},
        }
        malformed = [
            None,
            {**valid, "id": ""},
            {**valid, "state": "closed"},
            {**valid, "agent_id": 7},
            {**valid, "released_at": True},
            {**valid, "evidence": []},
            {**valid, "evidence": {"alternate_close": "done"}},
            {**valid, "evidence": {"close": ""}},
        ]
        for slot in malformed:
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                agent_slot_ledger.released_slot_projection(slot)
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                agent_slot_ledger.released_slot_close_evidence_sha256(slot)


if __name__ == "__main__": unittest.main()
