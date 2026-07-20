import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).parents[1]
SHARED = REPO / "skills/_shared/verification_ledger.py"
WRAPPER = REPO / "skills/verify-plan/scripts/verification_ledger.py"


def canonical_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def digest(value):
    payload = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


class VerificationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan_bytes = b"# Plan\n\nGrounded behavior.\n"
        (self.root / "plan.md").write_bytes(self.plan_bytes)
        (self.root / "evidence.json").write_text(
            json.dumps({"fact": "observed"}), encoding="utf-8"
        )
        (self.root / "dependency.txt").write_bytes(b"available\n")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, script, *args):
        return subprocess.run(
            ["python3", str(script), *map(str, args)],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def _approval_ref(self, attempt_id, snapshot_path, snapshot_sha, approval):
        return {
            "critic_attempt_id": attempt_id,
            "critic_snapshot_path": snapshot_path,
            "critic_snapshot_sha256": snapshot_sha,
            "approval_sha256": digest(approval),
        }

    def _finding(self, *, status="open"):
        core = {
            "id": "F1",
            "classification": "FIX NOW",
            "obligation_ids": ["O1"],
            "iteration_first_seen": 1,
        }
        return {**core, "fingerprint": digest(core), "status": status}

    def _build_plan_ledger(
        self,
        *,
        obligation_ids=("O1",),
        specs=None,
        findings=None,
        coverage_status="checked",
        inventory_decision="APPROVED",
    ):
        specs = specs or [
            {"iteration": 1, "obligation_id": "O1", "status": "SUPPORTED"}
        ]
        findings = findings or []
        plan_sha = digest(self.plan_bytes)
        section = {
            "id": "S1",
            "path": "plan.md",
            "start_line": 1,
            "end_line": 3,
            "content_sha256": digest(self.plan_bytes),
        }
        evidence = {
            "id": "E1",
            "source_ref": {
                "repository_key": "task",
                "path": "evidence.json",
                "selector": "/fact",
            },
            "content_sha256": digest("observed"),
        }
        dependency = {
            "id": "D1",
            "source_ref": {
                "repository_key": "task",
                "path": "dependency.txt",
                "selector": "WHOLE_FILE",
            },
            "content_sha256": digest(b"available\n"),
        }
        evidence_revision_sha = digest({
            "evidence_items": [evidence],
            "dependencies": [dependency],
        })
        obligations = []
        for obligation_id in obligation_ids:
            obligation = {
                "id": obligation_id,
                "coverage_id": "C01",
                "claim": f"Claim {obligation_id}",
                "plan_section_refs": ["S1"],
                "evidence_refs": ["E1"],
                "dependency_refs": ["D1"],
            }
            binding_projection = {
                "id": obligation["id"],
                "coverage_id": obligation["coverage_id"],
                "claim": obligation["claim"],
                "plan_sections": [section],
                "evidence_items": [evidence],
                "dependencies": [dependency],
            }
            obligations.append(
                {**obligation, "binding_sha256": digest(binding_projection)}
            )

        inventory_projection = {
            "contract_version": 1,
            "plan_sha256": plan_sha,
            "evidence_revision_sha256": evidence_revision_sha,
            "plan_sections": [section],
            "evidence_items": [evidence],
            "dependencies": [dependency],
            "obligations": obligations,
        }
        inventory_sha = digest(inventory_projection)
        inventory_approval = {
            "inventory_sha256": inventory_sha,
            "plan_sha256": plan_sha,
            "evidence_revision_sha256": evidence_revision_sha,
            "decision": inventory_decision,
            "rationale": "The finite inventory covers the declared surface.",
            "evidence": ["S1", "E1", "D1"],
        }

        obligation_map = {item["id"]: item for item in obligations}
        assessments = []
        assignments = []
        critic_outputs = []
        grouped = {}
        for spec in specs:
            grouped.setdefault(spec["iteration"], []).append(spec)

        inventory_approval_ref = None
        for iteration in sorted(grouped):
            attempt_id = f"critic-{iteration}"
            snapshot_path = f".verify-plan/critic-outputs/{attempt_id}.json"
            assignment_ids = sorted(item["obligation_id"] for item in grouped[iteration])
            assignment_projection = {
                "iteration": iteration,
                "inventory_sha256": inventory_sha,
                "assigned_obligation_ids": assignment_ids,
            }
            assignments.append(
                {**assignment_projection, "assignment_sha256": digest(assignment_projection)}
            )
            pending_assessments = []
            approval_objects = []
            for spec in grouped[iteration]:
                obligation = obligation_map[spec["obligation_id"]]
                status = spec["status"]
                finding_snapshots = spec.get("finding_snapshots", [])
                blocked_boundary = None
                if status == "BLOCKED":
                    blocked_boundary = {
                        "type": "RUNTIME",
                        "binding_kind": "DEPENDENCY",
                        "binding_id": "D1",
                        "observed_content_sha256": dependency["content_sha256"],
                        "required_change": "The frozen runtime capability must change.",
                    }
                assessment_projection = {
                    "iteration": iteration,
                    "obligation_id": obligation["id"],
                    "binding_sha256": obligation["binding_sha256"],
                    "status": status,
                    "evidence": [
                        {
                            "registry_kind": "PLAN_SECTION",
                            "id": "S1",
                            "claim": "The frozen plan states the behavior.",
                        }
                    ],
                    "finding_snapshots": finding_snapshots,
                    "blocked_boundary": blocked_boundary,
                }
                assessment_fingerprint = digest(assessment_projection)
                approval = {
                    "iteration": iteration,
                    "obligation_id": obligation["id"],
                    "binding_sha256": obligation["binding_sha256"],
                    "assessment_fingerprint": assessment_fingerprint,
                    "decision": "APPROVED",
                    "rationale": "The assessment matches the frozen evidence.",
                    "evidence": ["S1"],
                }
                pending_assessments.append(
                    ({**assessment_projection, "assessment_fingerprint": assessment_fingerprint}, approval)
                )
                approval_objects.append(approval)

            snapshot = {
                "schema_version": 1,
                "attempt_id": attempt_id,
                "inventory_approval": inventory_approval if iteration == 1 else None,
                "assessment_approvals": sorted(approval_objects, key=digest),
                "coverage_exclusion_approvals": [],
            }
            snapshot_bytes = canonical_bytes(snapshot)
            snapshot_file = self.root / snapshot_path
            snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            snapshot_file.write_bytes(snapshot_bytes)
            snapshot_sha = digest(snapshot_bytes)
            critic_outputs.append(
                {
                    "attempt_id": attempt_id,
                    "snapshot_path": snapshot_path,
                    "output_sha256": snapshot_sha,
                }
            )
            if iteration == 1:
                inventory_approval_ref = self._approval_ref(
                    attempt_id, snapshot_path, snapshot_sha, inventory_approval
                )
            for assessment, approval in pending_assessments:
                assessments.append(
                    {
                        **assessment,
                        "approval": approval,
                        "approval_ref": self._approval_ref(
                            attempt_id, snapshot_path, snapshot_sha, approval
                        ),
                    }
                )

        inventory = {
            "inventory_sha256": inventory_sha,
            "plan_sha256": plan_sha,
            "evidence_revision_sha256": evidence_revision_sha,
            "plan_sections": [section],
            "evidence_items": [evidence],
            "dependencies": [dependency],
            "obligations": obligations,
            "completeness_approval": inventory_approval,
            "completeness_approval_ref": inventory_approval_ref,
        }
        ledger = {
            "kind": "plan",
            "target": "plan.md",
            "active_plan_sha256": plan_sha,
            "iteration": max(grouped, default=0),
            "created_at": "2026-07-18T00:00:00+00:00",
            "coverage_queue": [
                {
                    "id": "C01",
                    "summary": "Primary surface",
                    "risk": "high",
                    "status": coverage_status,
                    "evidence_to_inspect": ["plan.md"],
                }
            ],
            "findings": findings,
            "iteration_log": [],
            "plan_verification": {
                "contract_version": 1,
                "plan_sha256": plan_sha,
                "evidence_revision_sha256": evidence_revision_sha,
                "inventory_sha256": inventory_sha,
                "inventories": [inventory],
                "assignments": assignments,
                "obligation_assessments": assessments,
                "critic_outputs": critic_outputs,
                "coverage_exclusion_approvals": [],
            },
        }
        path = self.root / "ledger.json"
        path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
        return path, ledger

    def test_plan_init_requires_revision_hashes_and_is_not_stoppable(self):
        missing = self.run_cli(SHARED, "init", "--kind", "plan")
        self.assertNotEqual(missing.returncode, 0)
        output = self.root / "init.json"
        plan_sha = "a" * 64
        evidence_sha = "b" * 64
        created = self.run_cli(
            SHARED,
            "init",
            "--kind",
            "plan",
            "--plan-sha256",
            plan_sha,
            "--evidence-revision-sha256",
            evidence_sha,
            "--output",
            output,
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        ledger = json.loads(output.read_text())
        self.assertIsNone(ledger["plan_verification"]["inventory_sha256"])
        self.assertEqual(self.run_cli(SHARED, "check", output).returncode, 0)
        self.assertNotEqual(
            self.run_cli(SHARED, "check", output, "--can-stop").returncode, 0
        )

    def test_analysis_and_work_initialization_remain_compatible(self):
        for kind in ("analysis", "work"):
            output = self.root / f"{kind}.json"
            created = self.run_cli(SHARED, "init", "--kind", kind, "-o", output)
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertNotIn("plan_verification", json.loads(output.read_text()))
            self.assertEqual(self.run_cli(SHARED, "check", output).returncode, 0)

    def test_valid_supported_inventory_can_stop(self):
        path, _ = self._build_plan_ledger()
        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        result = self.run_cli(SHARED, "check", path, "--can-stop")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_ledger_rejects_conflicting_root_plan_identity(self):
        path, ledger = self._build_plan_ledger()
        ledger["active_plan_sha256"] = "f" * 64
        path.write_text(json.dumps(ledger), encoding="utf-8")
        result = self.run_cli(SHARED, "check", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active_plan_sha256 conflicts", result.stderr)

    def test_plan_ledger_rejects_target_content_drift(self):
        path, _ = self._build_plan_ledger()
        (self.root / "plan.md").write_text("# Changed\n", encoding="utf-8")
        result = self.run_cli(SHARED, "check", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target content does not match", result.stderr)

    def test_portable_plan_ledger_prefers_its_adjacent_target(self):
        path, _ = self._build_plan_ledger()
        (self.root / ".git").mkdir()
        snapshot = self.root / "snapshots" / "ledger"
        snapshot.mkdir(parents=True)
        for relative in (
            "plan.md",
            "evidence.json",
            "dependency.txt",
            ".verify-plan/critic-outputs/critic-1.json",
        ):
            source = self.root / relative
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        portable = snapshot / "verification-ledger.json"
        portable.write_bytes(path.read_bytes())
        (self.root / "plan.md").unlink()

        result = self.run_cli(SHARED, "check", portable, "--can-stop")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_ledger_rejects_unrecomputable_evidence_revision(self):
        path, ledger = self._build_plan_ledger()
        verification = ledger["plan_verification"]
        verification["evidence_revision_sha256"] = "f" * 64
        verification["inventories"][0]["evidence_revision_sha256"] = "f" * 64
        path.write_text(json.dumps(ledger), encoding="utf-8")
        result = self.run_cli(SHARED, "check", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence_revision_sha256 mismatch", result.stderr)

    def test_plan_ledger_rejects_assessment_foreign_registry_id(self):
        path, ledger = self._build_plan_ledger()
        assessment = ledger["plan_verification"]["obligation_assessments"][0]
        assessment["evidence"][0]["id"] = "UNKNOWN"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        result = self.run_cli(SHARED, "check", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown registry id for the owning inventory", result.stderr)

    def test_plan_ledger_rejects_blocked_foreign_binding_id(self):
        path, ledger = self._build_plan_ledger(
            specs=[{"iteration": 1, "obligation_id": "O1", "status": "BLOCKED"}],
            coverage_status="unverified",
        )
        boundary = ledger["plan_verification"]["obligation_assessments"][0]["blocked_boundary"]
        boundary["binding_id"] = "UNKNOWN"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        result = self.run_cli(SHARED, "check", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("blocked_boundary names an unknown registry id", result.stderr)

    def test_plan_ledger_rejects_blocked_observed_hash_mismatch(self):
        path, ledger = self._build_plan_ledger(
            specs=[{"iteration": 1, "obligation_id": "O1", "status": "BLOCKED"}],
            coverage_status="unverified",
        )
        boundary = ledger["plan_verification"]["obligation_assessments"][0]["blocked_boundary"]
        boundary["observed_content_sha256"] = "f" * 64
        path.write_text(json.dumps(ledger), encoding="utf-8")
        result = self.run_cli(SHARED, "check", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("observed content hash mismatch", result.stderr)

    def test_partial_slice_returns_next_obligation(self):
        path, _ = self._build_plan_ledger(
            obligation_ids=("O1", "O2"), coverage_status="unverified"
        )
        result = self.run_cli(SHARED, "next-assignment", path, "--limit", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["next_obligation_ids"], ["O2"])

    def test_next_assignment_emits_priority_slice_in_canonical_order(self):
        path, ledger = self._build_plan_ledger(
            obligation_ids=("O-A", "O-B"),
            specs=[{"iteration": 1, "obligation_id": "O-A", "status": "SUPPORTED"}],
            coverage_status="unverified",
        )
        ledger["iteration"] = 0
        ledger["coverage_queue"][0]["risk"] = "low"
        ledger["coverage_queue"].append(
            {
                "id": "C02",
                "summary": "Higher-risk surface",
                "risk": "high",
                "status": "unverified",
                "evidence_to_inspect": ["plan.md"],
            }
        )
        verification = ledger["plan_verification"]
        inventory = verification["inventories"][0]
        obligation = inventory["obligations"][1]
        obligation["coverage_id"] = "C02"
        obligation["binding_sha256"] = digest(
            {
                "id": obligation["id"],
                "coverage_id": obligation["coverage_id"],
                "claim": obligation["claim"],
                "plan_sections": inventory["plan_sections"],
                "evidence_items": inventory["evidence_items"],
                "dependencies": inventory["dependencies"],
            }
        )
        inventory_projection = {
            "contract_version": 1,
            "plan_sha256": inventory["plan_sha256"],
            "evidence_revision_sha256": inventory["evidence_revision_sha256"],
            "plan_sections": inventory["plan_sections"],
            "evidence_items": inventory["evidence_items"],
            "dependencies": inventory["dependencies"],
            "obligations": inventory["obligations"],
        }
        inventory["inventory_sha256"] = digest(inventory_projection)
        inventory["completeness_approval"] = None
        inventory["completeness_approval_ref"] = None
        verification["inventory_sha256"] = inventory["inventory_sha256"]
        verification["assignments"] = []
        verification["obligation_assessments"] = []
        verification["critic_outputs"] = []
        path.write_text(json.dumps(ledger), encoding="utf-8")

        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        result = self.run_cli(SHARED, "next-assignment", path, "--limit", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["next_obligation_ids"], ["O-A", "O-B"]
        )

    def test_next_assignment_requires_approved_inventory(self):
        path, _ = self._build_plan_ledger(
            inventory_decision="REJECTED", coverage_status="unverified"
        )
        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        result = self.run_cli(SHARED, "next-assignment", path, "--limit", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inventory-not-approved", result.stderr)

    def test_next_assignment_bootstraps_never_reviewed_inventory(self):
        path, ledger = self._build_plan_ledger(coverage_status="unverified")
        ledger["iteration"] = 0
        ledger["plan_verification"]["assignments"] = []
        ledger["plan_verification"]["obligation_assessments"] = []
        ledger["plan_verification"]["critic_outputs"] = []
        inventory = ledger["plan_verification"]["inventories"][0]
        inventory["completeness_approval"] = None
        inventory["completeness_approval_ref"] = None
        path.write_text(json.dumps(ledger), encoding="utf-8")
        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        result = self.run_cli(SHARED, "next-assignment", path, "--limit", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["next_obligation_ids"], ["O1"])

    def test_next_assignment_refuses_pending_assignment(self):
        path, ledger = self._build_plan_ledger(coverage_status="unverified")
        ledger["plan_verification"]["obligation_assessments"] = []
        output = ledger["plan_verification"]["critic_outputs"][0]
        snapshot_path = self.root / output["snapshot_path"]
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["assessment_approvals"] = []
        snapshot_bytes = canonical_bytes(snapshot)
        snapshot_path.write_bytes(snapshot_bytes)
        snapshot_sha = digest(snapshot_bytes)
        output["output_sha256"] = snapshot_sha
        inventory = ledger["plan_verification"]["inventories"][0]
        inventory["completeness_approval_ref"]["critic_snapshot_sha256"] = snapshot_sha
        path.write_text(json.dumps(ledger), encoding="utf-8")
        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        result = self.run_cli(SHARED, "next-assignment", path, "--limit", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assignment-pending", result.stderr)

    def test_blocked_obligation_blocks_stop_and_assignment(self):
        path, _ = self._build_plan_ledger(
            specs=[{"iteration": 1, "obligation_id": "O1", "status": "BLOCKED"}],
            coverage_status="unverified",
        )
        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        self.assertNotEqual(
            self.run_cli(SHARED, "check", path, "--can-stop").returncode, 0
        )
        result = self.run_cli(SHARED, "next-assignment", path, "--limit", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("blocked-obligation", result.stderr)

    def test_later_finding_reset_is_valid_and_rescheduled(self):
        finding = self._finding(status="open")
        path, ledger = self._build_plan_ledger(
            findings=[finding], coverage_status="unverified"
        )
        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        self.assertNotEqual(
            self.run_cli(SHARED, "check", path, "--can-stop").returncode, 0
        )
        result = self.run_cli(SHARED, "next-assignment", path, "--limit", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["next_obligation_ids"], ["O1"])
        ledger["coverage_queue"][0]["status"] = "checked"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        self.assertNotEqual(self.run_cli(SHARED, "check", path).returncode, 0)

    def test_resolved_gap_requires_later_supported_and_derives_fixed(self):
        finding = self._finding(status="resolved")
        snapshot = {key: finding[key] for key in (
            "id", "fingerprint", "classification", "obligation_ids", "iteration_first_seen"
        )}
        path, _ = self._build_plan_ledger(
            specs=[
                {
                    "iteration": 1,
                    "obligation_id": "O1",
                    "status": "GAP",
                    "finding_snapshots": [snapshot],
                },
                {"iteration": 2, "obligation_id": "O1", "status": "SUPPORTED"},
            ],
            findings=[finding],
            coverage_status="fixed",
        )
        self.assertEqual(self.run_cli(SHARED, "check", path).returncode, 0)
        self.assertEqual(
            self.run_cli(SHARED, "check", path, "--can-stop").returncode, 0
        )

    def test_critic_snapshot_tamper_fails(self):
        path, ledger = self._build_plan_ledger()
        snapshot = self.root / ledger["plan_verification"]["critic_outputs"][0]["snapshot_path"]
        snapshot.write_bytes(snapshot.read_bytes() + b"\n")
        self.assertNotEqual(self.run_cli(SHARED, "check", path).returncode, 0)

    def test_legacy_plan_ledger_fails_public_commands(self):
        legacy = self.root / "legacy.json"
        legacy.write_text(
            json.dumps(
                {
                    "kind": "plan",
                    "target": "plan.md",
                    "iteration": 1,
                    "coverage_queue": [],
                    "findings": [],
                    "iteration_log": [],
                }
            ),
            encoding="utf-8",
        )
        for args in (("check", legacy), ("check", legacy, "--can-stop"), ("next-assignment", legacy, "--limit", "1")):
            result = self.run_cli(SHARED, *args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("plan-obligation-contract-required", result.stderr)

    def test_real_wrapper_matches_shared_plan_init_and_check(self):
        shared_path = self.root / "shared.json"
        wrapper_path = self.root / "wrapper.json"
        common = (
            "init", "--kind", "plan", "--plan-sha256", "a" * 64,
            "--evidence-revision-sha256", "b" * 64,
        )
        self.assertEqual(
            self.run_cli(SHARED, *common, "-o", shared_path).returncode, 0
        )
        self.assertEqual(
            self.run_cli(WRAPPER, *common, "-o", wrapper_path).returncode, 0
        )
        shared = json.loads(shared_path.read_text())
        wrapped = json.loads(wrapper_path.read_text())
        datetime.fromisoformat(shared.pop("created_at"))
        datetime.fromisoformat(wrapped.pop("created_at"))
        self.assertEqual(shared, wrapped)
        self.assertEqual(self.run_cli(WRAPPER, "check", wrapper_path).returncode, 0)


if __name__ == "__main__":
    unittest.main()
