import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("state", ROOT/"skills/_shared/convergence_state.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)


class StateTests(unittest.TestCase):
    def make_state(self, root):
        req=root/"requirements.json"; req.write_text(json.dumps([{"id":"R1","text":"x","source":"user"}]))
        state=root/"state.json"; source=root/"source"; source.write_text("x")
        cli=["python3",str(ROOT/"skills/_shared/convergence_state.py")]
        subprocess.run(cli+["init",str(state),"--source",str(source),"--objective","o","--requirements-file",str(req)],check=True,capture_output=True)
        return state,cli
    def stage_ready(self,state,root,status="review"):
        managed=root/"baseline"; managed.mkdir(exist_ok=True); (managed/"x").write_text("x")
        data=json.loads(state.read_text()); digest=s.digest_tree(managed); data["status"]=status; data["managed_paths"]={str(managed):{"baseline_hash":digest,"expected_hash":digest,"allowed_children":[]}}; state.write_text(json.dumps(data)); return data
    def test_task_id_is_stable(self):
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw)/"task.json"
            self.assertEqual(s.task_id(source,"objective"), s.task_id(source,"objective"))

    def test_managed_baseline_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); req=root/"requirements.json"; req.write_text(json.dumps([{"id":"R1","text":"x","source":"user"}]))
            state=root/"state.json"; source=root/"source"; source.write_text("x"); managed=root/"managed"; managed.mkdir(); (managed/"x").write_text("one")
            base=["python3",str(ROOT/"skills/_shared/convergence_state.py")]
            subprocess.run(base+["init",str(state),"--source",str(source),"--objective","o","--requirements-file",str(req)],check=True,capture_output=True)
            subprocess.run(base+["init-baseline",str(state),"--managed-path",str(managed)],check=True,capture_output=True)
            self.assertEqual(subprocess.run(base+["guard-baseline",str(state)]).returncode,0)
            (managed/"x").write_text("two")
            self.assertEqual(subprocess.run(base+["guard-baseline",str(state)]).returncode,3)

    def test_managed_child_scope_ignores_unrelated_siblings(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); managed=root/"managed"; owned=managed/"owned"; unrelated=managed/"unrelated"; owned.mkdir(parents=True); unrelated.mkdir(); (owned/"x").write_text("one"); (unrelated/"x").write_text("one")
            subprocess.run(cli+["init-baseline",str(state),"--managed-path",str(managed),"--managed-child",str(owned)],check=True,capture_output=True)
            (unrelated/"x").write_text("two"); self.assertEqual(subprocess.run(cli+["guard-baseline",str(state)],capture_output=True).returncode,0)
            (owned/"x").write_text("two"); self.assertEqual(subprocess.run(cli+["guard-baseline",str(state)],capture_output=True).returncode,3)

    def test_structured_approval_has_resolved_scope(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); req=root/"r"; req.write_text(json.dumps([{"id":"R1","text":"x","source":"u"}]))
            state=root/"s"; source=root/"source"; source.write_text("x"); cli=["python3",str(ROOT/"skills/_shared/convergence_state.py")]
            subprocess.run(cli+["init",str(state),"--source",str(source),"--objective","o","--requirements-file",str(req)],check=True,capture_output=True)
            subprocess.run(cli+["grant-approval",str(state),"--id","a","--kind","commit","--operations",'["commit"]',"--repository-roots",json.dumps([str(root)]),"--stage","review","--evidence","user"],check=True,capture_output=True)
            scope=json.loads(state.read_text())["approvals"]["a"]["scope"]
            self.assertEqual(scope["kind"],"commit"); self.assertEqual(scope["repository_roots"],[str(root.resolve())])

    def test_complete_rejects_open_gap_and_missing_baseline(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text())
            data["status"]="review"; data["requirements"]["R1"]["status"]="satisfied"; data["gaps"]["G1"]={"status":"open"}; state.write_text(json.dumps(data))
            self.assertNotEqual(subprocess.run(cli+["transition",str(state),"--to","complete"],capture_output=True).returncode,0)

    def test_stage_result_persists_new_gap_and_rejects_false_pass(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); result=root/"result.json"
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"GAPS","open_gap_ids":["G1"],"closed_gap_ids":[],"new_gaps":[{"id":"G1","requirement_ids":["R1"],"source_stage":"review","impact":"x","evidence":"e","status":"open"}],"new_blockers":[],"record_transitions":[],"evidence":["e"],"artifact_paths":[]}))
            subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            self.assertEqual(json.loads(state.read_text())["gaps"]["G1"]["status"],"open")
            result2=root/"pass.json"; payload=json.loads(result.read_text()); payload.update(attempt=2,verdict="PASS"); result2.write_text(json.dumps(payload))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result2)],capture_output=True).returncode,0)

    def test_artifact_snapshot_survives_source_update_and_detects_snapshot_tamper(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); artifact=root/"evidence"; artifact.write_text("one")
            subprocess.run(cli+["register-artifact",str(state),"--id","a","--path",str(artifact),"--kind","ledger","--stage","review"],check=True,capture_output=True)
            subprocess.run(cli+["record-stage",str(state),"--stage","review","--attempt","1","--verdict","PASS","--artifact-id","a"],check=True,capture_output=True)
            artifact.write_text("two"); self.assertEqual(subprocess.run(cli+["check",str(state)],capture_output=True).returncode,0)
            snapshot=Path(json.loads(state.read_text())["artifacts"]["a"]["snapshot_path"]); snapshot.write_text("tampered")
            self.assertNotEqual(subprocess.run(cli+["check",str(state)],capture_output=True).returncode,0)

    def test_legacy_artifact_migration_records_source_advance_without_rewriting_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); artifact=root/"evidence"; artifact.write_text("one")
            registered_hash=s.digest_tree(artifact); data=json.loads(state.read_text())
            data["artifacts"]["a"]={"id":"a","path":str(artifact),"hash":registered_hash,"type":"ledger","stage":"review"}
            data["stages"]["review:1:1"]={"stage":"review","outer_iteration":1,"attempt":1,"verdict":"PASS","artifact_ids":["a"]}
            state.write_text(json.dumps(data)); artifact.write_text("two")
            self.assertNotEqual(subprocess.run(cli+["check",str(state)],capture_output=True).returncode,0)
            subprocess.run(cli+["migrate-artifact-provenance",str(state)],check=True,capture_output=True)
            checked=subprocess.run(cli+["check",str(state)],capture_output=True,text=True)
            self.assertEqual(checked.returncode,0); self.assertIn("legacy artifact source advanced",checked.stdout)
            migrated=json.loads(state.read_text()); self.assertEqual(migrated["artifacts"]["a"]["hash"],registered_hash)
            event=migrated["artifact_provenance_events"]["a"]
            self.assertEqual(event["registered_hash"],registered_hash); self.assertEqual(event["observed_hash"],s.digest_tree(artifact))

    def test_unrelated_repo_change_does_not_block_allowed_path_guard(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); repo=root/"repo"; repo.mkdir()
            subprocess.run(["git","-C",str(repo),"init","-q"],check=True); subprocess.run(["git","-C",str(repo),"config","user.email","test@example.com"],check=True); subprocess.run(["git","-C",str(repo),"config","user.name","Test"],check=True)
            (repo/"AGENTS.md").write_text("owned"); (repo/"unrelated.py").write_text("one")
            subprocess.run(["git","-C",str(repo),"add","."],check=True); subprocess.run(["git","-C",str(repo),"commit","-qm","base"],check=True)
            state,cli=self.make_state(root)
            subprocess.run(cli+["init-baseline",str(state),"--repository",str(repo),"--allowed-path",str(repo/"AGENTS.md")],check=True,capture_output=True)
            (repo/"unrelated.py").write_text("two")
            self.assertEqual(subprocess.run(cli+["guard-baseline",str(state)],capture_output=True).returncode,0)
            (repo/"AGENTS.md").write_text("changed")
            self.assertEqual(subprocess.run(cli+["guard-baseline",str(state)],capture_output=True).returncode,3)

    def test_index_only_allowed_path_drift_is_blocked(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); repo=root/"repo"; repo.mkdir()
            subprocess.run(["git","-C",str(repo),"init","-q"],check=True); subprocess.run(["git","-C",str(repo),"config","user.email","test@example.com"],check=True); subprocess.run(["git","-C",str(repo),"config","user.name","Test"],check=True)
            target=repo/"AGENTS.md"; target.write_text("base"); subprocess.run(["git","-C",str(repo),"add","."],check=True); subprocess.run(["git","-C",str(repo),"commit","-qm","base"],check=True)
            state,cli=self.make_state(root); subprocess.run(cli+["init-baseline",str(state),"--repository",str(repo),"--allowed-path",str(target)],check=True,capture_output=True)
            target.write_text("staged"); subprocess.run(["git","-C",str(repo),"add","AGENTS.md"],check=True); target.write_text("base")
            self.assertEqual(subprocess.run(cli+["guard-baseline",str(state)],capture_output=True).returncode,3)

    def test_unrelated_head_advance_does_not_block_allowed_path_guard(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); repo=root/"repo"; repo.mkdir()
            subprocess.run(["git","-C",str(repo),"init","-q"],check=True); subprocess.run(["git","-C",str(repo),"config","user.email","test@example.com"],check=True); subprocess.run(["git","-C",str(repo),"config","user.name","Test"],check=True)
            (repo/"AGENTS.md").write_text("owned"); (repo/"unrelated.py").write_text("one"); subprocess.run(["git","-C",str(repo),"add","."],check=True); subprocess.run(["git","-C",str(repo),"commit","-qm","base"],check=True)
            state,cli=self.make_state(root); subprocess.run(cli+["init-baseline",str(state),"--repository",str(repo),"--allowed-path",str(repo/"AGENTS.md")],check=True,capture_output=True)
            (repo/"unrelated.py").write_text("two"); subprocess.run(["git","-C",str(repo),"add","unrelated.py"],check=True); subprocess.run(["git","-C",str(repo),"commit","-qm","unrelated"],check=True)
            self.assertEqual(subprocess.run(cli+["guard-baseline",str(state)],capture_output=True).returncode,0)

    def test_malformed_new_gap_cannot_pass(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); result=root/"result.json"
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[{"id":"bad","requirement_ids":["R1"],"impact":"x","evidence":"e"}],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_protected_generated_overlap_requires_explicit_flag(self):
        text=(ROOT/"skills/_shared/convergence_state.py").read_text()
        self.assertIn("--accept-generated-overlap",text)
        self.assertIn("protected AGENTS.md changed outside generated region",text)
        self.assertIn("generated overlap is limited to AGENTS.md",text)

    def test_pass_cannot_introduce_open_blocker(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); result=root/"result.json"
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[{"id":"B1","source_stage":"review","status":"open","impact":"cannot verify","unblock":"supply evidence"}],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_blocked_requires_and_owns_open_blocker(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); result=root/"result.json"
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"BLOCKED","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[{"id":"B1","type":"execution","source_stage":"review","status":"open","impact":"cannot verify","unblock":"supply evidence"}],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            data=json.loads(state.read_text()); self.assertEqual(data["stages"]["review:1:1"]["owned_blocker_ids"],["B1"])

    def test_exclusion_requires_matching_approval(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root)
            denied=subprocess.run(cli+["set-requirement",str(state),"--id","R1","--status","excluded","--evidence","out of scope"],capture_output=True)
            self.assertNotEqual(denied.returncode,0)
            subprocess.run(cli+["grant-approval",str(state),"--id","exclude-r1","--kind","exclude","--operations",'["exclude"]',"--target-ids",'["R1"]',"--stage","review","--evidence","Kamen approved exclusion"],check=True,capture_output=True)
            command=cli+["set-requirement",str(state),"--id","R1","--status","excluded","--evidence","out of scope","--approval-id","exclude-r1","--operation-id","exclude-r1-op","--stage","review"]
            subprocess.run(command,check=True,capture_output=True); subprocess.run(command,check=True,capture_output=True)
            data=json.loads(state.read_text()); self.assertEqual(data["approvals"]["exclude-r1"]["status"],"consumed")
            denied_reuse=command.copy(); denied_reuse[denied_reuse.index("exclude-r1-op")]="different-op"
            self.assertNotEqual(subprocess.run(denied_reuse,capture_output=True).returncode,0)

    def test_cap_reached_cannot_use_generic_resume(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text())
            data.update(status="cap_reached",blocked_from_status="review",cap_stage="review",cap_attempt=3); state.write_text(json.dumps(data))
            self.assertNotEqual(subprocess.run(cli+["resume",str(state),"--stage","review"],capture_output=True).returncode,0)

    def test_approval_blocker_cannot_use_generic_resume(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text())
            data.update(status="blocked",blocked_from_status="implementation",blocked_stage="implementation")
            data["blockers"]["B1"]={"status":"open","stage":"implementation","reason":"approval needed","required_evidence":"Kamen approval","resolution":"approval"}; state.write_text(json.dumps(data))
            self.assertNotEqual(subprocess.run(cli+["resume",str(state),"--blocker-id","B1","--evidence","claimed"],capture_output=True).returncode,0)

    def test_resume_requires_terminal_blocker_and_consumes_approval(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text())
            data.update(status="blocked",blocked_from_status="implementation",blocked_stage="implementation")
            data["blockers"]["B1"]={"status":"open","stage":"implementation","reason":"tool failed","required_evidence":"passing rerun","resolution":"evidence"}; state.write_text(json.dumps(data))
            self.assertNotEqual(subprocess.run(cli+["resume",str(state),"--blocker-id","B1"],capture_output=True).returncode,0)
            data=json.loads(state.read_text()); data["blockers"]["B1"].update(status="closed",closure_evidence="verified transcript"); state.write_text(json.dumps(data))
            subprocess.run(cli+["grant-approval",str(state),"--id","resume-b1","--kind","resume","--operations",'["resume"]',"--target-ids",'["B1"]',"--stage","implementation","--evidence","Kamen approved"],check=True,capture_output=True)
            command=cli+["resume",str(state),"--blocker-id","B1","--approval-id","resume-b1","--operation-id","resume-b1-op"]
            subprocess.run(command,check=True,capture_output=True); subprocess.run(command,check=True,capture_output=True)
            self.assertEqual(json.loads(state.read_text())["approvals"]["resume-b1"]["status"],"consumed")

    def test_new_blocker_cannot_overwrite_existing_blocker(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); result=root/"result.json"
            data["blockers"]["B1"]={"status":"open","stage":"review","reason":"missing evidence","required_evidence":"supply evidence"}; state.write_text(json.dumps(data))
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":["B1"],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[{"id":"B1","source_stage":"review","status":"closed","impact":"missing evidence","unblock":"supply evidence"}],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)
            self.assertEqual(json.loads(state.read_text())["blockers"]["B1"]["status"],"open")

    def test_new_gap_cannot_overwrite_existing_gap(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); result=root/"result.json"
            self.stage_ready(state,root); data=json.loads(state.read_text()); data["requirements"]["R1"]["status"]="satisfied"; data["gaps"]["G1"]={"id":"G1","requirement_ids":["R1"],"source_stage":"review","impact":"broken","evidence":"red","status":"open"}; state.write_text(json.dumps(data))
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":["G1"],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":["G1"],"new_gaps":[{"id":"G1","requirement_ids":["R1"],"source_stage":"review","impact":"broken","evidence":"red","status":"closed"}],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)
            self.assertEqual(json.loads(state.read_text())["gaps"]["G1"]["status"],"open")

    def test_approval_blocker_resolves_with_matching_approval(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text())
            data.update(status="blocked",blocked_from_status="implementation",blocked_stage="implementation")
            data["blockers"]["B1"]={"status":"open","stage":"implementation","reason":"approval needed","required_evidence":"Kamen approval","resolution":"approval"}; state.write_text(json.dumps(data))
            subprocess.run(cli+["grant-approval",str(state),"--id","resume-b1","--kind","resume","--operations",'["resolve-blocker"]',"--target-ids",'["B1"]',"--stage","implementation","--evidence","Kamen approved"],check=True,capture_output=True)
            subprocess.run(cli+["resolve-approval-blocker",str(state),"--blocker-id","B1","--approval-id","resume-b1","--operation-id","resolve-b1"],check=True,capture_output=True)
            data=json.loads(state.read_text()); self.assertEqual(data["status"],"implementation"); self.assertEqual(data["blockers"]["B1"]["status"],"closed"); self.assertEqual(data["approvals"]["resume-b1"]["status"],"consumed")

    def test_cap_reached_continues_with_matching_approval(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text())
            data.update(status="cap_reached",blocked_from_status="review",cap_stage="review",cap_attempt=3); state.write_text(json.dumps(data))
            subprocess.run(cli+["grant-approval",str(state),"--id","continue-review","--kind","continue","--operations",'["continue"]',"--target-ids",'["review"]',"--stage","review","--evidence","Kamen approved"],check=True,capture_output=True)
            command=cli+["continue-stage",str(state),"--stage","review","--approval-id","continue-review","--operation-id","continue-review-op"]
            subprocess.run(command,check=True,capture_output=True); subprocess.run(command,check=True,capture_output=True)
            data=json.loads(state.read_text()); self.assertEqual(data["status"],"review"); self.assertEqual(data["approvals"]["continue-review"]["status"],"consumed")
            data.update(status="cap_reached",blocked_from_status="review",cap_stage="review",cap_attempt=4); state.write_text(json.dumps(data))
            denied=command.copy(); denied[denied.index("continue-review-op")]="different-op"
            self.assertNotEqual(subprocess.run(denied,capture_output=True).returncode,0)

    def test_open_gap_closure_requires_transition_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); result=root/"result.json"
            self.stage_ready(state,root); data=json.loads(state.read_text())
            data["requirements"]["R1"]["status"]="satisfied"; data["gaps"]["G1"]={"id":"G1","requirement_ids":["R1"],"source_stage":"review","impact":"broken","evidence":"red","status":"open"}; state.write_text(json.dumps(data))
            payload={"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":["G1"],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":["G1"],"new_gaps":[],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}
            result.write_text(json.dumps(payload)); self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)
            payload["record_transitions"]=[{"kind":"gap","id":"G1","from_status":"open","to_status":"closed","evidence":"green reproduction transcript"}]
            result.write_text(json.dumps(payload)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            data=json.loads(state.read_text()); self.assertEqual(data["gaps"]["G1"]["status"],"closed"); self.assertEqual(data["gaps"]["G1"]["closure_evidence"],"green reproduction transcript")

    def test_gap_superseded_and_non_gap_terminal_paths(self):
        for target in ("superseded","non-gap"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); data=json.loads(state.read_text()); result=root/"result.json"
                data["requirements"]["R1"]["status"]="satisfied"; data["gaps"]["G1"]={"id":"G1","requirement_ids":["R1"],"source_stage":"review","impact":"old","evidence":"red","status":"open"}
                if target == "superseded": data["gaps"]["G2"]={"id":"G2","requirement_ids":["R1"],"source_stage":"other","impact":"replacement","evidence":"red","status":"open"}
                state.write_text(json.dumps(data)); transition={"kind":"gap","id":"G1","from_status":"open","to_status":target,"evidence":"critic evidence"}
                if target == "superseded": transition["replacement_id"]="G2"
                payload={"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":["G1"],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":["G1"],"new_gaps":[],"new_blockers":[],"record_transitions":[transition],"evidence":[],"artifact_paths":[]}
                result.write_text(json.dumps(payload)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
                self.assertEqual(json.loads(state.read_text())["gaps"]["G1"]["status"],target)

    def test_stage_rejects_unknown_owned_blocker(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); result=root/"result.json"
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":["missing"],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_execution_blocker_fix_verify_close_and_resume(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); result=root/"result.json"; data=json.loads(state.read_text()); data["requirements"]["R1"]["status"]="satisfied"; state.write_text(json.dumps(data))
            base={"stage":"review","iteration":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":["B1"],"open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"evidence":[],"artifact_paths":[]}
            first={**base,"attempt":1,"verdict":"BLOCKED","new_blockers":[{"id":"B1","type":"execution","source_stage":"review","status":"open","impact":"tool failed","unblock":"passing rerun"}],"record_transitions":[]}
            result.write_text(json.dumps(first)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            self.assertEqual(json.loads(state.read_text())["status"],"blocked")
            for attempt,from_status,to_status,verdict in ((2,"open","fixed-awaiting-verification","BLOCKED"),(3,"fixed-awaiting-verification","verified","BLOCKED"),(4,"verified","closed","PASS")):
                payload={**base,"attempt":attempt,"verdict":verdict,"new_blockers":[],"record_transitions":[{"kind":"blocker","id":"B1","from_status":from_status,"to_status":to_status,"evidence":f"{to_status} evidence"}]}
                result.write_text(json.dumps(payload)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            self.assertEqual(json.loads(state.read_text())["blockers"]["B1"]["status"],"closed")
            subprocess.run(cli+["grant-approval",str(state),"--id","resume-b1","--kind","resume","--operations",'["resume"]',"--target-ids",'["B1"]',"--stage","review","--evidence","Kamen approved"],check=True,capture_output=True)
            subprocess.run(cli+["resume",str(state),"--blocker-id","B1","--approval-id","resume-b1","--operation-id","resume-b1-op"],check=True,capture_output=True)
            self.assertEqual(json.loads(state.read_text())["status"],"review")

    def test_consumed_approval_id_cannot_be_regranted(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root)
            grant=cli+["grant-approval",str(state),"--id","exclude-r1","--kind","exclude","--operations",'["exclude"]',"--target-ids",'["R1"]',"--stage","review","--evidence","Kamen approved"]
            subprocess.run(grant,check=True,capture_output=True)
            subprocess.run(cli+["set-requirement",str(state),"--id","R1","--status","excluded","--evidence","out of scope","--approval-id","exclude-r1","--operation-id","exclude-r1-op","--stage","review"],check=True,capture_output=True)
            self.assertNotEqual(subprocess.run(grant,capture_output=True).returncode,0)

    def test_direct_record_ids_are_immutable(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root)
            gap=cli+["record-gap",str(state),"--id","G1","--requirement-ids",'["R1"]',"--source-stage","review","--impact","broken","--evidence","red"]
            subprocess.run(gap,check=True,capture_output=True); changed=gap.copy(); changed[changed.index("broken")]="different"
            self.assertNotEqual(subprocess.run(changed,capture_output=True).returncode,0)
            blocker=cli+["block",str(state),"--id","B1","--type","execution","--stage","review","--reason","tool failed","--required-evidence","passing rerun","--resolution","evidence"]
            subprocess.run(blocker,check=True,capture_output=True); changed=blocker.copy(); changed[changed.index("tool failed")]="different"
            self.assertNotEqual(subprocess.run(changed,capture_output=True).returncode,0)

    def test_review_pass_rejects_open_assigned_requirement(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); result=root/"result.json"
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_completion_rejects_nonterminal_blocker(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); managed=root/"managed"; managed.mkdir(); (managed/"x").write_text("x")
            data.update(status="review",managed_paths={str(managed):{"baseline_hash":s.digest_tree(managed),"expected_hash":s.digest_tree(managed)}})
            data["requirements"]["R1"]["status"]="satisfied"; data["blockers"]["B1"]={"status":"fixed-awaiting-verification"}; data["stages"]["review:1:1"]={"stage":"review","outer_iteration":1,"attempt":1,"verdict":"PASS"}; state.write_text(json.dumps(data))
            self.assertNotEqual(subprocess.run(cli+["transition",str(state),"--to","complete"],capture_output=True).returncode,0)

    def test_resume_rejects_another_nonterminal_blocker(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); data.update(status="blocked",blocked_from_status="implementation",blocked_stage="implementation")
            data["blockers"]={"B1":{"status":"closed","stage":"implementation"},"B2":{"status":"open","stage":"implementation"}}; state.write_text(json.dumps(data))
            subprocess.run(cli+["grant-approval",str(state),"--id","resume","--kind","resume","--operations",'["resume"]',"--target-ids",'["B1"]',"--stage","implementation","--evidence","Kamen approved"],check=True,capture_output=True)
            self.assertNotEqual(subprocess.run(cli+["resume",str(state),"--blocker-id","B1","--approval-id","resume","--operation-id","resume-op"],capture_output=True).returncode,0)

    def test_stage_rejects_unowned_blocker_transition(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); result=root/"result.json"
            data["blockers"]["B1"]={"status":"open","stage":"review"}; state.write_text(json.dumps(data))
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"GAPS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[],"record_transitions":[{"kind":"blocker","id":"B1","from_status":"open","to_status":"fixed-awaiting-verification","evidence":"fix"}],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_scope_approval_is_consumed_by_add_requirement(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root)
            subprocess.run(cli+["grant-approval",str(state),"--id","scope","--kind","scope-change","--operations",'["add-requirement"]',"--target-ids",'["R2","R3"]',"--stage","review","--evidence","Kamen approved"],check=True,capture_output=True)
            subprocess.run(cli+["add-requirement",str(state),"--id","R2","--text","two","--source","user","--approval-id","scope","--operation-id","add-r2","--stage","review"],check=True,capture_output=True)
            self.assertNotEqual(subprocess.run(cli+["add-requirement",str(state),"--id","R3","--text","three","--source","user","--approval-id","scope","--operation-id","add-r3","--stage","review"],capture_output=True).returncode,0)

    def test_candidate_requirement_resolution_applies_and_replays(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); data.update(status="blocked",blocked_from_status="review",blocked_stage="review")
            data["blockers"]["B1"]={"status":"open","type":"approval","stage":"review","resolution":"approval","candidate_requirement":{"id":"R2","text":"two","source":"review","discovered_by_stage":"review"}}; state.write_text(json.dumps(data))
            subprocess.run(cli+["grant-approval",str(state),"--id","scope","--kind","scope-change","--operations",'["approve-candidate"]',"--target-ids",'["B1"]',"--stage","review","--evidence","Kamen approved"],check=True,capture_output=True)
            command=cli+["resolve-approval-blocker",str(state),"--blocker-id","B1","--approval-id","scope","--operation-id","scope-op","--decision","approve"]
            subprocess.run(command,check=True,capture_output=True); subprocess.run(command,check=True,capture_output=True)
            data=json.loads(state.read_text()); self.assertEqual(data["requirements"]["R2"]["status"],"open"); self.assertEqual(data["status"],"research"); self.assertEqual(data["outer_iteration"],2)

    def test_gaps_cannot_start_closed_and_support_terminal_transitions(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root)
            self.assertNotEqual(subprocess.run(cli+["record-gap",str(state),"--id","G1","--requirement-ids",'["R1"]',"--source-stage","review","--impact","x","--evidence","e","--status","closed"],capture_output=True).returncode,0)
            result=root/"result.json"; closed={"id":"G1","requirement_ids":["R1"],"source_stage":"review","impact":"x","evidence":"e","status":"closed"}
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"GAPS","open_gap_ids":[],"closed_gap_ids":["G1"],"new_gaps":[closed],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_stage_exact_replay_and_attempt_order(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); data=json.loads(state.read_text()); data["requirements"]["R1"]["status"]="satisfied"; state.write_text(json.dumps(data)); result=root/"result.json"
            payload={"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}
            result.write_text(json.dumps(payload)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            payload["attempt"]=99; result.write_text(json.dumps(payload)); self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_artifact_id_is_immutable(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); one=root/"one"; two=root/"two"; one.write_text("1"); two.write_text("2")
            subprocess.run(cli+["register-artifact",str(state),"--id","A","--path",str(one),"--kind","evidence","--stage","review"],check=True,capture_output=True)
            self.assertNotEqual(subprocess.run(cli+["register-artifact",str(state),"--id","A","--path",str(two),"--kind","evidence","--stage","review"],capture_output=True).returncode,0)

    def test_baseline_and_stage_order_are_enforced(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); result=root/"result.json"
            self.assertNotEqual(subprocess.run(cli+["transition",str(state),"--to","plan"],capture_output=True).returncode,0)
            result.write_text(json.dumps({"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"GAPS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[]}))
            self.assertNotEqual(subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],capture_output=True).returncode,0)

    def test_requirement_and_approval_transitions_are_typed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); result=root/"result.json"
            subprocess.run(cli+["grant-approval",str(state),"--id","A","--kind","resume","--operations",'[]',"--stage","review","--evidence","obsolete"],check=True,capture_output=True)
            payload={"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[],"record_transitions":[{"kind":"requirement","id":"R1","from_status":"open","to_status":"satisfied","evidence":"end-to-end review"},{"kind":"approval","id":"A","from_status":"granted","to_status":"revoked","evidence":"superseded"}],"evidence":[],"artifact_paths":[]}
            result.write_text(json.dumps(payload)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            data=json.loads(state.read_text()); self.assertEqual(data["requirements"]["R1"]["status"],"satisfied"); self.assertEqual(data["approvals"]["A"]["status"],"revoked")

    def test_check_rejects_malformed_blocker_lifecycle(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); data["blockers"]["B1"]={"status":"resolved"}; state.write_text(json.dumps(data))
            self.assertNotEqual(subprocess.run(cli+["check",str(state)],capture_output=True).returncode,0)

    def test_stage_artifacts_are_content_versioned(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); self.stage_ready(state,root); data=json.loads(state.read_text()); data["requirements"]["R1"]["status"]="satisfied"; state.write_text(json.dumps(data)); artifact=root/"evidence"; artifact.write_text("one"); result=root/"result.json"
            payload={"stage":"review","iteration":1,"attempt":1,"assigned_requirement_ids":["R1"],"assigned_gap_ids":[],"owned_blocker_ids":[],"verdict":"PASS","open_gap_ids":[],"closed_gap_ids":[],"new_gaps":[],"new_blockers":[],"record_transitions":[],"evidence":[],"artifact_paths":[str(artifact)]}
            result.write_text(json.dumps(payload)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            artifact.write_text("two"); payload["attempt"]=2; result.write_text(json.dumps(payload)); subprocess.run(cli+["record-stage",str(state),"--result-file",str(result)],check=True,capture_output=True)
            data=json.loads(state.read_text()); first=data["stages"]["review:1:1"]["artifact_ids"]; second=data["stages"]["review:1:2"]["artifact_ids"]
            self.assertNotEqual(first,second); self.assertEqual(subprocess.run(cli+["check",str(state)],capture_output=True).returncode,0)

    def test_candidate_ids_are_reserved_and_provenance_required(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); state,cli=self.make_state(root); data=json.loads(state.read_text()); data.update(status="blocked",blocked_from_status="review",blocked_stage="review"); data["blockers"]["B1"]={"status":"open","type":"approval","stage":"review","resolution":"approval","candidate_requirement":{"id":"R2","text":"two","source":"review"}}; state.write_text(json.dumps(data))
            subprocess.run(cli+["grant-approval",str(state),"--id","add","--kind","scope-change","--operations",'["add-requirement"]',"--target-ids",'["R2"]',"--stage","review","--evidence","approved"],check=True,capture_output=True)
            self.assertNotEqual(subprocess.run(cli+["add-requirement",str(state),"--id","R2","--text","two","--source","review","--approval-id","add","--operation-id","add-r2","--stage","review"],capture_output=True).returncode,0)
            subprocess.run(cli+["grant-approval",str(state),"--id","scope","--kind","scope-change","--operations",'["approve-candidate"]',"--target-ids",'["B1"]',"--stage","review","--evidence","approved"],check=True,capture_output=True)
            self.assertNotEqual(subprocess.run(cli+["resolve-approval-blocker",str(state),"--blocker-id","B1","--approval-id","scope","--operation-id","scope-op","--decision","approve"],capture_output=True).returncode,0)


if __name__ == "__main__": unittest.main()
