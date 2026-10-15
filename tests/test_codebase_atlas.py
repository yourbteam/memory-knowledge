# Opt-in Development-Probe adapter for the captured worker94 failed-no-answer boundary.
if __name__ == "__main__" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "--atlas-worker94-failed-job-dpp":
    import hashlib as _h, json as _j, os as _o, shutil as _sh, subprocess as _sp, sys as _s
    from pathlib import Path as _P
    from datetime import datetime as _dt, timezone as _tz
    _work=_P(_o.environ["EXPERIMENT_WORK_DIR"]).resolve(); _work.mkdir(parents=True,exist_ok=True)
    _result=_P(_o.environ["EXPERIMENT_RESULT_PATH"]); _feed=_P(_o.environ["EXPERIMENT_TELEMETRY_PATH"])
    _index=_P(_o.environ["ATLAS_FAILED_JOB_INDEX_PATH"]).resolve(strict=True); _index_raw=_index.read_bytes()
    _index_sha=_o.environ["ATLAS_FAILED_JOB_INDEX_SHA256"]
    if _h.sha256(_index_raw).hexdigest()!=_index_sha: raise SystemExit("captured failed-job index hash mismatch")
    _proof=_j.loads(_index_raw); _case=_s.argv[2]
    _source=_P(__file__).resolve().parents[1]/"skills/codebase-atlas-machinery/scripts/task_continuation.py"
    _candidate_sha=_h.sha256(_source.read_bytes()).hexdigest(); _seq=0; _observations=[]
    def _emit(kind,msg,digest,obs):
        global _seq
        _seq+=1; row={"schema_version":1,"sequence":_seq,"recorded_at":_dt.now(_tz.utc).isoformat(),"event":kind,"message":msg,"evidence_sha256":digest,"observations":obs}
        _feed.parent.mkdir(parents=True,exist_ok=True)
        with _feed.open("a",encoding="utf-8") as f:f.write(_j.dumps(row,sort_keys=True)+"\n");f.flush()
    def _tree(root): return {str(p.relative_to(root)):_h.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    def _call(run,valid_index=True):
        argv=[_s.executable,"-B",str(_source),"resume","--repo","/Users/kamenkamenov/taggable-api","--db","/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite","--task-file","/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt","--intake-run","/private/tmp/atlas-discount-lifecycle-task-20261012/run","--run-dir",str(run),"--engine-manifest","/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json","--max-worker-calls","1","--timeout-seconds","180","--prepare-only","--adopt-checkpoint-executor"]
        if valid_index: argv += ["--failed-worker-evidence-index",str(_index),"--failed-worker-evidence-index-sha256",_index_sha]
        else: argv += ["--failed-worker-evidence-index",str(_index),"--failed-worker-evidence-index-sha256","0"*64]
        p=_sp.run(argv,capture_output=True,text=True,timeout=180,env={**_o.environ,"PYTHONDONTWRITEBYTECODE":"1"})
        try: body=_j.loads(p.stdout)
        except Exception: body=None
        return {"argv":argv,"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"body":body}
    try:
        if _case not in {"valid-index-adoption","wrong-index-refusal","captured-file-mutation-refusal","post-admission-index-mutation-refusal"}: raise SystemExit("unknown captured case")
        run=_work/"child-run"; _sh.copytree(_P(_proof["candidate_root"]),run)
        before=_tree(run); _initial_events=len(list((run/"events").glob("*.json")))
        if _case=="wrong-index-refusal":
            call=_call(run,False); after=_tree(run)
            if call["exit_code"]!=2 or after!=before: raise SystemExit("wrong index was not refused mutation-free")
            _observations.append({"case":_case,"refused":True,"old_files_preserved":True,"provider_calls":0})
        elif _case=="captured-file-mutation-refusal":
            target=run/"workers"/"existing_map_task_fit_4ea1336ed5155b917796da39"/"events.jsonl"
            target.write_bytes(target.read_bytes()+b"\n")
            mutated=_tree(run); call=_call(run); after=_tree(run)
            if call["exit_code"]!=2 or after!=mutated or len(list((run/"events").glob("*.json")))!=_initial_events: raise SystemExit("mutated captured failure was not refused mutation-free")
            _observations.append({"case":_case,"refused":True,"mutation_preserved":after==mutated,"provider_calls":0})
        else:
            call=_call(run); after=_tree(run); adopted=(run/"events/000063.json")
            if call["exit_code"]!=0 or not call["body"] or call["body"].get("events")!=63 or call["body"].get("status")!="existing_map_task_fit_4ea1336ed5155b917796da39": raise SystemExit("valid captured failure adoption did not preserve the pending task-fit status")
            if any(after.get(k)!=v for k,v in before.items()): raise SystemExit("valid adoption changed a preexisting file")
            event=_j.loads(adopted.read_bytes())
            if event.get("payload",{}).get("failed_evidence_index_sha256")!=_index_sha: raise SystemExit("adoption event did not bind the explicit frozen index")
            if _case=="post-admission-index-mutation-refusal":
                snap=run/"inputs/engine-transition/failed-event62-evidence-index.json"; snap.write_bytes(snap.read_bytes()+b" ")
                after_mutation=_tree(run); verify=_sp.run([_s.executable,"-B",str(_source),"status","--repo","/Users/kamenkamenov/taggable-api","--db","/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite","--task-file","/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt","--intake-run","/private/tmp/atlas-discount-lifecycle-task-20261012/run","--run-dir",str(run),"--engine-manifest","/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json"],capture_output=True,text=True,timeout=180,env={**_o.environ,"PYTHONDONTWRITEBYTECODE":"1"})
                if verify.returncode!=2 or _tree(run)!=after_mutation: raise SystemExit("post-admission index mutation was not refused")
                _observations.append({"case":_case,"refused":True,"after_admission_hash_guard":True,"provider_calls":0})
            else:
                _observations.append({"case":_case,"adopted":True,"old_files_preserved":True,"pending_status":call["body"]["status"],"event_count":63,"retry_eligibility_preflight":"passed through public resume using _load runtime context","retry_started_events":0,"provider_calls":0})
        _raw={"case_id":_case,"candidate_module_sha256":_candidate_sha,"evidence_index_sha256":_index_sha,"provider_calls":0,"observations":_observations}
        _raw["result_sha256"]=_h.sha256(_j.dumps(_raw,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        _result.parent.mkdir(parents=True,exist_ok=True);_result.write_text(_j.dumps(_raw,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        _emit("worker94-captured-failure-case-completed",_case,_raw["result_sha256"],_observations)
    except Exception as _exc:
        _emit("worker94-captured-failure-case-failed",str(_exc),_h.sha256(str(_exc).encode()).hexdigest(),_observations);raise
    raise SystemExit(0)

# Opt-in Development-Probe adapter for the completed-worker recovery boundary.
if __name__ == "__main__" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "--atlas-completed-worker-recovery-dpp":
    import hashlib as _h, json as _j, os as _o, shutil as _sh, subprocess as _sp, sys as _s
    from pathlib import Path as _P
    from datetime import datetime as _dt, timezone as _tz
    _work=_P(_o.environ["EXPERIMENT_WORK_DIR"]).resolve(); _work.mkdir(parents=True,exist_ok=True)
    _input=_P(_o.environ["EXPERIMENT_INPUT_PATH"]).resolve(strict=True); _result=_P(_o.environ["EXPERIMENT_RESULT_PATH"]); _feed=_P(_o.environ["EXPERIMENT_TELEMETRY_PATH"])
    _variant=_o.environ["EXPERIMENT_VARIANT_ID"]
    _cfg_path=_P(_o.environ["EXPERIMENT_VARIANT_PATH"]) if _o.environ.get("EXPERIMENT_VARIANT_PATH") else None
    _cfg=_j.loads(_cfg_path.read_bytes())["configuration"] if _cfg_path else {}
    _case=_cfg.get("case_id"); _approach=_s.argv[2]
    _proof_path=_P(_o.environ["ATLAS_RECOVERY_PROOF_INDEX"]).resolve(strict=True); _proof_raw=_proof_path.read_bytes()
    if _h.sha256(_proof_raw).hexdigest()!=_o.environ["ATLAS_RECOVERY_PROOF_INDEX_SHA256"]: raise SystemExit("recovery proof index digest mismatch")
    _proof=_j.loads(_proof_raw)
    _input_sha=_h.sha256(_input.read_bytes()).hexdigest()
    if _case is None:
        _matches=[name for name,digest in _proof["case_sha256"].items() if digest==_input_sha]
        _case=_matches[0] if len(_matches)==1 else None
    _case_sha=_proof["case_sha256"].get(_case)
    if not _case_sha or _input_sha!=_case_sha: raise SystemExit("captured case input identity mismatch")
    _candidate=_P(__file__).resolve().parents[1]/"skills/codebase-atlas-machinery/scripts/task_continuation.py"
    _candidate_sha=_h.sha256(_candidate.read_bytes()).hexdigest(); _script=_s.executable; _seq=0
    def _emit(kind,msg,digest,obs):
        global _seq
        _seq+=1; row={"schema_version":1,"sequence":_seq,"event":kind,"recorded_at":_dt.now(_tz.utc).isoformat(),"variant_id":_variant,"message":msg,"evidence_sha256":digest,"observations":obs}
        _feed.parent.mkdir(parents=True,exist_ok=True)
        with _feed.open("a",encoding="utf-8") as f:f.write(_j.dumps(row,sort_keys=True)+"\n");f.flush()
    def _tree(root): return {str(p.relative_to(root)):_h.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    def _call(argv):
        p=_sp.run(argv,capture_output=True,text=True,timeout=180,env={**_o.environ,"PYTHONDONTWRITEBYTECODE":"1"})
        try: body=_j.loads(p.stdout)
        except Exception: body=None
        return {"argv":argv,"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"body":body}
    _raw={"case_id":_case,"case_input_sha256":_case_sha,"approach_id":_approach,"candidate_module_sha256":_candidate_sha,"proof_index_sha256":_h.sha256(_proof_raw).hexdigest(),"provider_calls":0,"external_replay":"captured-terminal-recovery-replay" if _approach=="completed-worker-recovery" else "none"}
    _case_task=_P(_proof["task_file"]); _intake=_P(_proof["intake_run"]); _db=_proof["db"]; _repo=_proof["repo"]
    def _base(run):
        return [_script,"-B",str(_candidate),"resume","--repo",_repo,"--db",_db,"--task-file",str(_case_task),"--intake-run",str(_intake),"--run-dir",str(run),"--engine-manifest",_proof["engine_manifest"],"--completed-worker-register",_proof["worker_register"],"--completed-worker-register-sha256",_proof["worker_register_sha256"],"--previous-engine-archive",_proof["previous_engine_archive"],"--max-worker-calls","1"]
    try:
        run=_work/"child-run"; _sh.copytree(_proof["pending_child"],run)
        before=_tree(run); original_count=len(list((run/"events").glob("*.json")))
        if _case=="saved-task-corruption":
            # Exercise the captured fail-closed task-identity boundary in an isolated intake copy.
            intake_copy=_work/"damaged-intake"; _sh.copytree(_intake,intake_copy)
            task_copy=intake_copy/"task.txt"; task_copy.write_bytes(task_copy.read_bytes()+b"\n[isolated captured-case corruption]\n")
            argv=_base(run)
            argv[argv.index("--task-file")+1]=str(task_copy)
            argv[argv.index("--intake-run")+1]=str(intake_copy)
        else:
            argv=_base(run)
        _raw["public_command"]=_call(argv); _raw["run_path"]=str(run); _raw["event_count_before"]=original_count
        _after=_tree(run); _raw["original_files_unchanged"]=all(_after.get(k)==v for k,v in before.items()); _raw["original_file_count"]=len(before)
        _raw["event_count_after"]=len(list((run/"events").glob("*.json")))
        _raw["event_types"]=[_j.loads(p.read_bytes()).get("type") for p in sorted((run/"events").glob("*.json"))]
        _raw["captured_interruption_proof_sha256"]=_proof["interruption_proof_sha256"] if _case=="interrupted-intake" else None
        _raw["captured_interruption_proof_matches"]=_h.sha256(_P(_proof["interruption_proof"]).read_bytes()).hexdigest()==_proof["interruption_proof_sha256"] if _case=="interrupted-intake" else None
        if _case=="interrupted-intake":
            _checkpoint=_j.loads(_P(_proof["interruption_checkpoint"]).read_bytes())
            _raw["pre_review_checkpoint_matches"]=all(_h.sha256((run/rel).read_bytes()).hexdigest()==digest for rel,digest in _checkpoint["files"].items() if (run/rel).is_file()) and all((run/rel).is_file() for rel in _checkpoint["files"])
        else: _raw["pre_review_checkpoint_matches"]=None
        if _approach=="completed-worker-recovery":
            body=_raw["public_command"].get("body") or {}; _out=run/"outputs"; _combined=_j.loads((_out/"map_review_combined.json").read_bytes()) if (_out/"map_review_combined.json").is_file() else {}
            _valid=_j.loads((_out/"map_review_validation.json").read_bytes()) if (_out/"map_review_validation.json").is_file() else {}
            _raw["semantic_review"]={"combined_sha256":_h.sha256((_out/"map_review_combined.json").read_bytes()).hexdigest() if (_out/"map_review_combined.json").is_file() else None,"validation_sha256":_h.sha256((_out/"map_review_validation.json").read_bytes()).hexdigest() if (_out/"map_review_validation.json").is_file() else None,"source_decision":_combined.get("source_review",{}).get("decision"),"task_fit_decision":_combined.get("task_fit",{}).get("decision"),"semantic_claim_numbers":_combined.get("task_fit",{}).get("semantic_claim_numbers"),"task_sha256":body.get("task_sha256"),"source_identity_sha256":body.get("source_identity_sha256"),"validation_result":_valid.get("result"),"validation_writes":_valid.get("writes")}
        _raw["engine_manifest_sha256"]=_h.sha256(_P(_proof["engine_manifest"]).read_bytes()).hexdigest()
        _raw["terminal_worker_register_sha256"]=_h.sha256(_P(_proof["worker_register"]).read_bytes()).hexdigest()
        payload={"schema_version":1,"variant_id":_variant,"status":"completed","outcome":{"raw":_raw},"metrics":{},"error":None}
        _result.parent.mkdir(parents=True,exist_ok=True); _result.write_text(_j.dumps(payload,sort_keys=True)+"\n")
        _emit("work_completed","Executed the public completed-worker recovery path against the exact frozen case; no provider was called.",_h.sha256(_j.dumps(_raw,sort_keys=True).encode()).hexdigest(),{"case_id":_case,"approach_id":_approach,"case_sha256":_case_sha,"candidate_module_sha256":_candidate_sha})
        print(_j.dumps(payload,sort_keys=True)); raise SystemExit(0)
    except Exception as _exc:
        _msg=f"completed-worker recovery operator failed: {type(_exc).__name__}: {_exc}"
        _emit("operator_error",_msg,_h.sha256(_msg.encode()).hexdigest(),{"case_id":_case,"approach_id":_approach,"case_sha256":_case_sha})
        raise

# Development-Probe operator adapter; invoked only by the immutable experiment bundle.
if __name__ == "__main__" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "--atlas-native-intake-experiment":
    import hashlib as _h, importlib.util as _iu, json as _j, os as _os, shutil as _sh, subprocess as _sp, sys as _s, time as _t
    from pathlib import Path as _P
    from datetime import datetime as _dt, timezone as _tz
    _work=_P(_os.environ["EXPERIMENT_WORK_DIR"]).resolve(); _input=_P(_os.environ["EXPERIMENT_INPUT_PATH"]).resolve()
    _result=_P(_os.environ["EXPERIMENT_RESULT_PATH"]); _telemetry=_P(_os.environ["EXPERIMENT_TELEMETRY_PATH"])
    _variant=_os.environ["EXPERIMENT_VARIANT_ID"]
    _expected={"approved-plain-task":"aafa008afa8300979c03575df85844af35f1a5ebe3a5f4bed679aac292942c2d","missing-native-intake":"96e6cd65baaea1b1ab5c43f6f07992349648b68da49637a84b17956fcf65ab75","saved-task-corruption":"e0506883d0b74f1d588f1bbd98d3ffc0e096374ecb6fcb6c91b6340e8fe2006f","interrupted-intake":"015129cfa6924d9b7bc022fb4b42436b6f71e0dd0e19719d46c6521bc0ab840f"}
    _raw_input=_input.read_bytes(); _input_sha=_h.sha256(_raw_input).hexdigest()
    _cfg=_j.loads(_P(_os.environ["EXPERIMENT_VARIANT_PATH"]).read_bytes())["configuration"] if _os.environ.get("EXPERIMENT_VARIANT_PATH") else {}
    _case=_cfg.get("case_id") or next((k for k,v in _expected.items() if v==_input_sha),None)
    if _case not in _expected or _input_sha != _expected[_case]: raise SystemExit("frozen captured-case identity mismatch")
    _context_path=_P("/private/tmp/atlas-discount-lifecycle-task-20261012/intake-experiment/input.json")
    _context_bytes=_context_path.read_bytes(); _context_sha="c3b68c62a0b4ad77de37123fcc02c3c67a66f77e674683867d48b6781cef6598"
    if _h.sha256(_context_bytes).hexdigest()!=_context_sha: raise SystemExit("frozen task context changed")
    _context=_j.loads(_context_bytes); _repo=_context["repo"]; _db=_context["db"]; _max=_context["max_bytes"]
    _task_bytes=_raw_input if _case=="approved-plain-task" else _context["task_text"].encode("utf-8")
    _task=_work/"task.txt"; _task.write_bytes(_task_bytes); _run=_work/"run"
    _source=_P(__file__).resolve().parents[1]/"skills/codebase-atlas-machinery/scripts"
    _entry=_source/"task_intake.py"
    _seq=0
    def _emit(event,message,evidence,observations,correction=None):
        global _seq
        _seq+=1
        rec={"schema_version":1,"sequence":_seq,"event":event,"recorded_at":_dt.now(_tz.utc).isoformat(),"variant_id":_variant,"message":message,"evidence_sha256":evidence,"observations":observations}
        if correction is not None: rec["correction"]=correction
        with _telemetry.open("a",encoding="utf-8") as f:f.write(_j.dumps(rec,sort_keys=True)+"\n");f.flush()
    def _call(argv):
        p=_sp.run(argv,capture_output=True,text=True,timeout=90,env={**_os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
        try: body=_j.loads(p.stdout)
        except (ValueError,TypeError): body=None
        return {"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"body":body}
    def _files(root): return {str(p.relative_to(root)): _h.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    try:
        if _os.environ.get("ATLAS_INTAKE_INJECT_OPERATOR_FAILURE")=="1":
            raise RuntimeError("injected operator failure proof")
        _base=[_s.executable,"-B",str(_entry)]; _args=["--repo",_repo,"--db",_db,"--task-file",str(_task),"--max-bytes",str(_max)]
        _raw={"case_id":_case,"case_input_sha256":_input_sha,"task_sha256":_h.sha256(_task_bytes).hexdigest()}
        _raw["start"]=_call(_base+["start","--run-dir",str(_run)]+_args)
        _raw["saved_task_sha256"]=_h.sha256((_run/"task.txt").read_bytes()).hexdigest(); _before=_files(_run)
        _raw["resume"]=_call(_base+["resume","--run-dir",str(_run)]+_args); _raw["status"]=_call(_base+["status","--run-dir",str(_run)])
        _raw["exact_retry_artifacts_unchanged"]=_before==_files(_run)
        _raw["events"]=[_j.loads(p.read_text()) for p in sorted((_run/"events").glob("*.json"))] if (_run/"events").exists() else []
        _bad=_work/"tampered"; _sh.copytree(_run,_bad); (_bad/"task.txt").write_text("Unexpected replacement task\n",encoding="utf-8"); _before=_files(_bad)
        _raw["tampered_status"]=_call(_base+["status","--run-dir",str(_bad)]); _raw["tamper_refusal_unchanged"]=_before==_files(_bad)
        _missing=_work/"missing-stored-task"; _sh.copytree(_run,_missing); (_missing/"task.txt").unlink(); _before=_files(_missing)
        _raw["missing_task_status"]=_call(_base+["status","--run-dir",str(_missing)])
        _raw["missing_task_start"]=_call(_base+["start","--run-dir",str(_missing)]+_args)
        _raw["missing_task_refusal_unchanged"]=_before==_files(_missing)
        _s.path.insert(0,str(_source)); _spec=_iu.spec_from_file_location("atlas_task_intake",_entry); _mod=_iu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
        _interrupted=_work/"interrupted"; _identity=_mod._source_identity(_repo,_db); _mod._bind_or_start(_interrupted,_task_bytes,_identity,_max,True)
        _raw["interrupted_artifacts"]={str(p.relative_to(_interrupted)):_j.loads(p.read_text()) for p in _interrupted.rglob("*.json")}
        _raw["interrupted_resume"]=_call(_base+["resume","--run-dir",str(_interrupted)]+_args)
        _refusal_run=_work/"missing-native-refusal"
        _raw["captured_refusal"]=_call([_s.executable,"-B",str(_source/"question_coordinator.py"),"prepare","--repo",_repo,"--db",_db,"--question-file",str(_task),"--run-dir",str(_refusal_run)])
        _payload={"schema_version":1,"variant_id":_variant,"status":"completed","outcome":{"raw":_raw},"metrics":{},"error":None}
        _bytes=(_j.dumps(_payload,ensure_ascii=True,sort_keys=True)+"\n").encode(); _result.write_bytes(_bytes)
        _emit("work_completed","Executed all four frozen intake checks through the candidate public CLI; result records raw command observations.",_h.sha256(_bytes).hexdigest(),{"case_id":_case,"case_input_sha256":_input_sha,"task_sha256":_raw["task_sha256"],"candidate_module_sha256":_h.sha256(_entry.read_bytes()).hexdigest()})
        print(_j.dumps(_payload,ensure_ascii=True,sort_keys=True))
    except Exception as _exc:
        _msg=f"operator execution failed: {type(_exc).__name__}: {_exc}"; _digest=_h.sha256(_msg.encode()).hexdigest()
        try:
            _emit("operator_error",_msg,_digest,{"case_id":_case,"case_input_sha256":_input_sha},correction="Inspect the retained command and telemetry evidence, correct the operator defect, then retry in a fresh run directory.")
        except Exception as _telemetry_exc:
            if hasattr(_exc,"add_note"): _exc.add_note(f"operator error telemetry could not be written: {type(_telemetry_exc).__name__}: {_telemetry_exc}")
        raise
    raise SystemExit(0)

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/atlas.py"
ATLAS_SPEC = importlib.util.spec_from_file_location("atlas_test_module", SCRIPT)
ATLAS = importlib.util.module_from_spec(ATLAS_SPEC)
ATLAS_SPEC.loader.exec_module(ATLAS)
LAUNCHER_PATH = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/compiler_index_launch.py"
LAUNCHER_SPEC = importlib.util.spec_from_file_location("atlas_compiler_index_launch_test_module", LAUNCHER_PATH)
LAUNCHER = importlib.util.module_from_spec(LAUNCHER_SPEC)
LAUNCHER_SPEC.loader.exec_module(LAUNCHER)
RUNTIME_LAUNCHER_PATH = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/runtime_index_launch.py"
RUNTIME_LAUNCHER_SPEC = importlib.util.spec_from_file_location("atlas_runtime_index_launch_test_module", RUNTIME_LAUNCHER_PATH)
RUNTIME_LAUNCHER = importlib.util.module_from_spec(RUNTIME_LAUNCHER_SPEC)
RUNTIME_LAUNCHER_SPEC.loader.exec_module(RUNTIME_LAUNCHER)
CONTINUATION_PATH = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/task_continuation.py"
CONTINUATION_SPEC = importlib.util.spec_from_file_location("atlas_final_map_continuation_test_module", CONTINUATION_PATH)
CONTINUATION = importlib.util.module_from_spec(CONTINUATION_SPEC)
CONTINUATION_SPEC.loader.exec_module(CONTINUATION)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", os.fspath(repo), *args], text=True).strip()


def runtime_producer_identity():
    def file_identity(path):
        resolved = path.resolve(strict=True)
        return {"path": resolved.as_posix(), "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()}

    return {"atlas_source": file_identity(SCRIPT),
            "runtime_launcher_source": file_identity(RUNTIME_LAUNCHER_PATH)}


class AtlasCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "atlas-test@example.invalid")
        git(self.repo, "config", "user.name", "Atlas Test")
        (self.repo / "a.txt").write_bytes(b"alpha\x00\n")
        (self.repo / "sub dir").mkdir()
        (self.repo / "sub dir" / "b.txt").write_bytes(b"beta\n")
        git(self.repo, "add", "--", ".")
        self.db = self.root / "atlas.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args: str, expect=0):
        result = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if expect is not None:
            self.assertEqual(result.returncode, expect, result.stderr)
        return result

    def synthetic_native_final_worker(self, root: Path, phase: str, role: str, model: str,
                                      request: dict[str, Any] | None = None, answer: str = "{}"):
        """Build a labeled synthetic provider edge using the exact current native-register shape."""
        job = root / "workers" / phase
        job.mkdir(parents=True)
        (job / "workspace").mkdir()
        outputs = root / "outputs"
        outputs.mkdir(exist_ok=True)
        cli_path = root / "pinned-cli"
        if not cli_path.exists():
            cli_path.write_bytes(b"synthetic pinned CLI fingerprint")
            cli_path.chmod(0o755)
        thread_id = f"synthetic-{phase}-thread"
        request = request or {"role": role, "prompt": f"synthetic exact prompt for {phase}", "schema": {"type": "object"},
                   "task_sha256": "a" * 64, "source_identity_sha256": "b" * 64,
                   "plan_sha256": "c" * 64, "history_tip_sha256": "d" * 64}
        rows = [{"type": "thread.started", "thread_id": thread_id}, {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": answer}},
                {"type": "turn.completed"}]
        files = {"answer.txt": answer.encode(),
                 "argv.json": json.dumps([os.fspath(cli_path), "exec", "--ignore-user-config", "--ignore-rules",
                    "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--model", model,
                    "-c", 'model_reasoning_effort="high"', "-c", "project_doc_max_bytes=0", "-c",
                    "features.shell_tool=false", "-c", 'web_search="disabled"', "--cd",
                    os.fspath(job / "workspace"), "--json", "--output-last-message", os.fspath(job / "answer.txt"),
                    "--output-schema", os.fspath(job / "cli-schema.json"), "-"]).encode(),
                 "cli-schema.json": json.dumps(CONTINUATION.route_autorun._cli_schema(request["schema"])).encode(),
                 "elapsed_ms.json": b'{"elapsed_ms": 1}',
                 "events.jsonl": ("\n".join(json.dumps(row) for row in rows) + "\n").encode(),
                 "prompt.txt": request["prompt"].encode(),
                 "schema.json": json.dumps(request["schema"]).encode(), "stderr.txt": b""}
        for name, raw in files.items():
            (job / name).write_bytes(raw)
        digests = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
        register = {"schema_version": 1, "kind": "completed-native-worker-turn", "worker_directory": phase,
                    "role": role, "model": model, "thread_id": thread_id,
                    "prompt_sha256": digests["prompt.txt"], "schema_sha256": digests["schema.json"],
                    "argv_sha256": digests["argv.json"], "answer_sha256": digests["answer.txt"],
                    "events_sha256": digests["events.jsonl"], "artifact_sha256": digests}
        register_path = root / "workers" / f"{phase}.completion-register.json"
        register_raw = (json.dumps(register, sort_keys=True, separators=(",", ":")) + "\n").encode()
        register_path.write_bytes(register_raw)
        register_sha = hashlib.sha256(register_raw).hexdigest()
        result = {"role": role, "model": model, "thread_id": thread_id, "usage": {}, "elapsed_ms": 1,
                  "artifact_dir": os.fspath(job.resolve()), "artifact_sha256": digests,
                  "completion_register_path": os.fspath(register_path), "completion_register_sha256": register_sha}
        (outputs / f"{phase}-worker.json").write_text(json.dumps(result), encoding="utf-8")
        answer_ref = {"path": f"outputs/{phase}.txt", "sha256": hashlib.sha256(answer.encode()).hexdigest(),
                      "bytes": len(answer.encode())}
        (root / answer_ref["path"]).write_bytes(answer.encode())
        event = {"type": f"{phase}_worker_completed", "payload": {"phase": phase, "role": role,
                 "worker_thread_id": thread_id, "worker_artifact_sha256": digests,
                 "answer_path": answer_ref["path"], "answer_sha256": answer_ref["sha256"],
                 "completion_register_path": f"workers/{phase}.completion-register.json",
                 "completion_register_sha256": register_sha}}
        return request, result, event, register_path, register_sha, digests

    def synthetic_native_admission(self, root: Path, cli_path: Path):
        return (mock.patch.object(CONTINUATION.route_autorun, "CLI", os.fspath(cli_path)),
                mock.patch.object(CONTINUATION.route_autorun, "CLI_SHA256", hashlib.sha256(cli_path.read_bytes()).hexdigest()),
                mock.patch.object(CONTINUATION.route_autorun, "admit_terminal",
                    side_effect=lambda rows, answer: {"accepted": True, "final_text": answer,
                        "thread_id": rows[0]["thread_id"], "usage": {}}))

    def test_captured104_stale_source_refusal_preserves_checkpoint(self):
        """Captured104 is not rebound with a receipt from another checkpoint."""
        captured = Path("/private/tmp/atlas-final-map-assembly-20261015/prototype5-proof/frozen-original104")
        if not (captured / "events/000104.json").is_file():
            self.skipTest("Immutable captured104 citation checkpoint unavailable")
        source = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/task_continuation.py"
        manifest = Path("/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json")
        run = self.root / "captured104-read-only"
        shutil.copytree(captured, run)
        before = {p.relative_to(run).as_posix(): CONTINUATION._file_sha(p) for p in run.rglob("*") if p.is_file()}
        command = [sys.executable, "-B", os.fspath(source), "resume", "--repo", "/Users/kamenkamenov/taggable-api",
            "--db", "/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite",
            "--task-file", "/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt",
            "--intake-run", "/private/tmp/atlas-discount-lifecycle-task-20261012/run", "--run-dir", os.fspath(run),
            "--engine-manifest", os.fspath(manifest), "--prepare-only", "--adopt-final-map-feedback-executor"]
        refused = subprocess.run(command, text=True, capture_output=True, check=False, timeout=180,
                                 env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        after = {p.relative_to(run).as_posix(): CONTINUATION._file_sha(p) for p in run.rglob("*") if p.is_file()}
        self.assertNotEqual(refused.returncode, 0)
        self.assertTrue(any(word in refused.stderr.lower() for word in ("source", "transition", "executor")), refused.stderr)
        self.assertEqual(after, before)
        events = CONTINUATION._events(run)
        self.assertEqual(events[-1]["type"], "final_map_revision_0002_review_completed")
        self.assertEqual(events[-1]["payload"]["decision"], "rejected")
    def index(self):
        return json.loads(self.cli("index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db)).stdout)

    def query(self, snapshot_id, *extra):
        return json.loads(self.cli(
            "query", "--db", os.fspath(self.db), "--snapshot", snapshot_id, *extra
        ).stdout)

    def graph(self, snapshot_id):
        return self.query(snapshot_id, "--graph")["source_graph"]

    def discover_routes(self, terms, max_tokens=10000, expect=0):
        return self.cli(
            "discover", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--terms", *terms, "--max-tokens", str(max_tokens), expect=expect,
        )

    def evidence_pack(self, route_fact_id, max_tokens=100000, expect=0):
        return self.cli(
            "evidence-pack", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route_fact_id, "--max-tokens", str(max_tokens), expect=expect,
        )

    def route_find(self, route_fact_id=None, *, http_method=None, route=None, max_tokens=10000, expect=0):
        selector = []
        if route_fact_id is not None:
            selector.extend(("--route-fact-id", route_fact_id))
        if http_method is not None:
            selector.extend(("--http-method", http_method))
        if route is not None:
            selector.extend(("--route", route))
        return self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                        *selector, "--max-tokens", str(max_tokens), expect=expect)

    def coverage(self, max_tokens=100000, offset=0, expect=0):
        return self.cli("coverage", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                        "--max-tokens", str(max_tokens), "--offset", str(offset), expect=expect)

    def impact(self, method, max_tokens=10000, expect=0):
        return self.cli("impact", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                        "--method", method, "--max-tokens", str(max_tokens), expect=expect)

    def test_compiler_index_launcher_prompts_in_order_and_preserves_child_exit(self):
        checkout = self.root / "checkout"
        (checkout / "src").mkdir(parents=True)
        (checkout / ".git").mkdir()
        project = checkout / "src" / "App.csproj"
        project.write_text("<Project />", encoding="utf-8")
        database = self.root / "atlas.sqlite"
        database.write_bytes(b"saved atlas db")
        dotnet = self.root / "dotnet"
        dotnet.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        dotnet.chmod(0o755)
        answers = iter([os.fspath(checkout), os.fspath(database), "src/App.csproj", "net8.0"])
        prompts = []
        calls = []

        def ask(prompt):
            prompts.append(prompt)
            return next(answers)

        def dispatch(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 17)

        result = LAUNCHER.main([], input_fn=ask, runner=dispatch,
                               environment={"ATLAS_DOTNET": os.fspath(dotnet)},
                               atlas_script=SCRIPT)
        self.assertEqual(result, 17)
        self.assertEqual(prompts, ["Repository checkout path: ", "Atlas database path: ",
                                   "Repository-relative project path: ", "Target framework moniker: "])
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        self.assertEqual(argv[1:], [os.fspath(SCRIPT), "compiler-index", "--repo", checkout.resolve().as_posix(),
                                    "--db", database.resolve().as_posix(), "--project", "src/App.csproj", "--framework", "net8.0"])
        self.assertEqual(kwargs["env"]["ATLAS_DOTNET"], dotnet.resolve().as_posix())
        self.assertIs(kwargs["check"], False)

    def test_compiler_index_launcher_cancellation_at_needed_sdk_prompt_does_not_dispatch(self):
        checkout = self.root / "checkout"
        (checkout / "src").mkdir(parents=True)
        (checkout / ".git").mkdir()
        (checkout / "src" / "App.csproj").write_text("<Project />", encoding="utf-8")
        database = self.root / "atlas.sqlite"
        database.write_bytes(b"unchanged")
        before = database.read_bytes()
        answers = iter([os.fspath(checkout), os.fspath(database), "src/App.csproj", "net8.0"])
        prompts = []
        calls = []

        def ask(prompt):
            prompts.append(prompt)
            if prompt.startswith("Path to executable"):
                raise EOFError
            return next(answers)

        result = LAUNCHER.main([], input_fn=ask, runner=lambda *args, **kwargs: calls.append(args),
                               environment={"PATH": ""}, atlas_script=SCRIPT)
        self.assertEqual(result, 130)
        self.assertEqual(prompts[-1], "Path to executable dotnet SDK host: ")
        self.assertEqual(calls, [])
        self.assertEqual(database.read_bytes(), before)

    def test_compiler_index_launcher_rejects_invalid_project_without_dispatch(self):
        checkout = self.root / "checkout"
        checkout.mkdir()
        (checkout / ".git").mkdir()
        database = self.root / "atlas.sqlite"
        database.write_bytes(b"unchanged")
        before = database.read_bytes()
        answers = iter([os.fspath(checkout), os.fspath(database), "../escape.csproj"])
        calls = []
        result = LAUNCHER.main([], input_fn=lambda _prompt: next(answers),
                               runner=lambda *args, **kwargs: calls.append(args),
                               environment={"PATH": ""}, atlas_script=SCRIPT)
        self.assertEqual(result, 2)
        self.assertEqual(calls, [])
        self.assertEqual(database.read_bytes(), before)

    def test_runtime_index_launcher_prompts_exact_interface_and_profile_then_dispatches(self):
        checkout = self.root / "checkout"
        (checkout / "src").mkdir(parents=True)
        (checkout / ".git").mkdir()
        (checkout / "src" / "App.csproj").write_text("<Project />", encoding="utf-8")
        database = self.root / "atlas.sqlite"
        database.write_bytes(b"saved atlas db")
        dotnet = self.root / "dotnet"
        dotnet.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        dotnet.chmod(0o755)
        answers = iter([os.fspath(checkout), os.fspath(database), "src/App.csproj", "net8.0",
                        "Taggable.Api.Infrastructure.AdminTourManagement.ITourAssetStorage", "both"])
        prompts = []
        calls = []

        def ask(prompt):
            prompts.append(prompt)
            return next(answers)

        def dispatch(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 17)

        result = RUNTIME_LAUNCHER.main([], input_fn=ask, runner=dispatch,
                                       environment={"ATLAS_DOTNET": os.fspath(dotnet)}, atlas_script=SCRIPT)
        self.assertEqual(result, 17)
        self.assertEqual(prompts, ["Repository checkout path: ", "Atlas database path: ",
                                   "Repository-relative project path: ", "Target framework moniker: ",
                                   "Exact source interface type (fully qualified): ",
                                   "Startup profile (local-storage, cloud-storage, or both): "])
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        self.assertEqual(argv[1:], [os.fspath(SCRIPT), "runtime-index", "--repo", checkout.resolve().as_posix(),
                                    "--db", database.resolve().as_posix(), "--project", "src/App.csproj",
                                    "--framework", "net8.0", "--interface",
                                    "Taggable.Api.Infrastructure.AdminTourManagement.ITourAssetStorage",
                                    "--profile", "both"])
        self.assertEqual(kwargs["env"]["ATLAS_DOTNET"], dotnet.resolve().as_posix())
        self.assertIs(kwargs["check"], False)

    def test_runtime_index_launcher_rejects_unqualified_interface_without_dispatch(self):
        checkout = self.root / "checkout"
        (checkout / "src").mkdir(parents=True)
        (checkout / ".git").mkdir()
        (checkout / "src" / "App.csproj").write_text("<Project />", encoding="utf-8")
        database = self.root / "atlas.sqlite"
        database.write_bytes(b"unchanged")
        before = database.read_bytes()
        answers = iter([os.fspath(checkout), os.fspath(database), "src/App.csproj", "net8.0", "ITourAssetStorage"])
        calls = []
        result = RUNTIME_LAUNCHER.main([], input_fn=lambda _prompt: next(answers),
                                      runner=lambda *args, **kwargs: calls.append(args),
                                      environment={"PATH": ""}, atlas_script=SCRIPT)
        self.assertEqual(result, 2)
        self.assertEqual(calls, [])
        self.assertEqual(database.read_bytes(), before)

    def test_runtime_observer_rejects_open_profile_configuration_before_sdk_or_artifact_writes(self):
        artifact_dir = self.root / "artifacts"
        request = {"schema_version": 1, "profile": "local-storage", "account_name_state": "nonempty",
                   "account_name_probe": "atlasprobe", "repo_root": os.fspath(self.root),
                   "project_path": "Missing.csproj", "framework": "net8.0", "entry_assembly_name": "App",
                   "interface_type_name": "Example.IStorage", "expected_runtime_type_name": "Example.Storage",
                   "observer_source_root": os.fspath(self.root), "artifact_dir": os.fspath(artifact_dir),
                   "producer_identity": runtime_producer_identity()}
        with mock.patch.dict(os.environ, {"ATLAS_DOTNET": "", "PATH": ""}):
            with self.assertRaisesRegex(RUNTIME_LAUNCHER.LaunchError, "closed profile configuration"):
                RUNTIME_LAUNCHER.launch(request)
        self.assertFalse(artifact_dir.exists())

    def test_runtime_launcher_rejects_a_stale_producer_source_hash_before_artifact_creation(self):
        artifact_dir = self.root / "stale-producer-artifacts"
        producer_identity = runtime_producer_identity()
        producer_identity["atlas_source"]["sha256"] = "0" * 64
        request = {"schema_version": 1, "producer_identity": producer_identity,
                   "profile": "local-storage", "account_name_state": "empty", "account_name_probe": None,
                   "repo_root": os.fspath(self.root), "project_path": "Missing.csproj", "framework": "net8.0",
                   "entry_assembly_name": "App", "interface_type_name": "Example.IStorage",
                   "expected_runtime_type_name": "Example.Storage", "observer_source_root": os.fspath(self.root),
                   "artifact_dir": os.fspath(artifact_dir)}
        with self.assertRaisesRegex(RUNTIME_LAUNCHER.LaunchError, "producer source changed"):
            RUNTIME_LAUNCHER.launch(request)
        self.assertFalse(artifact_dir.exists())

    def test_runtime_launcher_rejects_symlinked_producer_source_ancestors(self):
        alias = self.root / "source-alias"
        alias.symlink_to(SCRIPT.parent, target_is_directory=True)
        producer_identity = runtime_producer_identity()
        producer_identity["atlas_source"]["path"] = (alias / SCRIPT.name).as_posix()
        artifact_dir = self.root / "symlink-producer-artifacts"
        request = {"schema_version": 1, "producer_identity": producer_identity,
                   "profile": "local-storage", "account_name_state": "empty", "account_name_probe": None,
                   "repo_root": os.fspath(self.root), "project_path": "Missing.csproj", "framework": "net8.0",
                   "entry_assembly_name": "App", "interface_type_name": "Example.IStorage",
                   "expected_runtime_type_name": "Example.Storage", "observer_source_root": os.fspath(self.root),
                   "artifact_dir": os.fspath(artifact_dir)}
        with self.assertRaisesRegex(RUNTIME_LAUNCHER.LaunchError, "path is not a regular absolute file"):
            RUNTIME_LAUNCHER.launch(request)
        self.assertFalse(artifact_dir.exists())

    def test_runtime_mirror_copies_only_source_build_inputs_and_excludes_configuration_files(self):
        source_root = self.root / "source"
        source_root.mkdir()
        files = {
            "Api.csproj": b"<Project />",
            "Program.cs": b"class Program {}",
            "appsettings.json": b"{\"PrivateKey\":\"must-not-copy\"}",
            "credentials.json": b"{\"token\":\"must-not-copy\"}",
            "asset.png": b"binary content is not needed before host build",
        }
        manifest = []
        for relative, content in files.items():
            path = source_root / relative
            path.write_bytes(content)
            manifest.append({"logical_path": f"tracked/{relative}", "path": relative,
                             "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content),
                             "presence": "present", "type": "file", "git_mode": "100644"})
        mirror = self.root / "mirror"
        mirror.mkdir()
        copied = RUNTIME_LAUNCHER._copy_manifest(source_root, mirror, manifest, generated=False)
        self.assertEqual({item["logical_path"] for item in copied},
                         {"tracked/Api.csproj", "tracked/Program.cs", "tracked/asset.png"})
        self.assertEqual((mirror / "Api.csproj").read_bytes(), files["Api.csproj"])
        self.assertEqual((mirror / "Program.cs").read_bytes(), files["Program.cs"])
        self.assertFalse((mirror / "appsettings.json").exists())
        self.assertFalse((mirror / "credentials.json").exists())
        self.assertEqual((mirror / "asset.png").read_bytes(), files["asset.png"])

    @unittest.skipUnless(os.environ.get("ATLAS_DOTNET"), "runtime observer fixture needs the approved local dotnet SDK")
    def test_runtime_launcher_captures_and_joins_a_real_framework_only_host(self):
        """This mechanics fixture exercises a built host; target profile proof is a separate captured case."""
        repo = self.root / "runtime-fixture"
        repo.mkdir()
        (repo / "FixtureHost.csproj").write_text(
            "<Project Sdk=\"Microsoft.NET.Sdk.Web\"><PropertyGroup><TargetFramework>net8.0</TargetFramework>"
            "<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><AssemblyName>FixtureHost</AssemblyName>"
            "</PropertyGroup></Project>", encoding="utf-8")
        (repo / "Program.cs").write_text(
            "using Microsoft.AspNetCore.Builder;\nusing Microsoft.Extensions.DependencyInjection;\n"
            "var builder = WebApplication.CreateBuilder(args);\n"
            "builder.Services.AddScoped<Demo.IStorage, Demo.LocalStorage>();\n"
            "var app = builder.Build();\n"
            "namespace Demo { public interface IStorage {} public sealed class LocalStorage : IStorage {} }\n",
            encoding="utf-8")
        empty_feed = self.root / "empty-nuget-feed"
        empty_feed.mkdir()
        nuget = self.root / "NuGet.Config"
        nuget.write_text(
            '<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear/><add key="empty" value="'
            + empty_feed.as_posix() + '"/></packageSources></configuration>', encoding="utf-8")
        dotnet = Path(os.environ["ATLAS_DOTNET"]).expanduser().resolve(strict=True)
        restore_env = dict(os.environ)
        restore_env.update({"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1"})
        restore = subprocess.run([dotnet.as_posix(), "restore", (repo / "FixtureHost.csproj").as_posix(),
                                  "--configfile", nuget.as_posix(), "--ignore-failed-sources"],
                                 cwd=repo, env=restore_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, timeout=60, check=False)
        self.assertEqual(restore.returncode, 0, restore.stderr or restore.stdout)
        tracked = []
        for relative in ("FixtureHost.csproj", "Program.cs"):
            content = (repo / relative).read_bytes()
            tracked.append({"logical_path": f"tracked/{relative}", "path": relative,
                            "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content),
                            "presence": "present", "type": "file", "git_mode": "100644"})
        generated = []
        for path in sorted((repo / "obj").rglob("*"), key=lambda item: os.fsencode(item.relative_to(repo).as_posix())):
            if path.is_symlink():
                self.fail(f"framework-only restore unexpectedly produced a symlink: {path}")
            if path.is_file():
                generated.append({"logical_path": path.relative_to(repo).as_posix(),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "size_bytes": path.stat().st_size})
        compiler_identity = {"tracked_inputs": tracked, "generated_inputs": generated}
        request = {
            "schema_version": 1, "snapshot_id": "a" * 64, "repo_root": repo.as_posix(),
            "project_path": "FixtureHost.csproj", "framework": "net8.0", "profile": "local-storage",
            "entry_assembly_name": "FixtureHost", "interface_type_name": "Demo.IStorage",
            "expected_runtime_type_name": "Demo.LocalStorage", "account_name_state": "empty",
            "account_name_probe": None,
            "observer_source_root": RUNTIME_LAUNCHER_PATH.parent.joinpath("runtime").as_posix(),
            "artifact_dir": (self.root / "runtime-artifacts").as_posix(),
            "tracked_inputs": tracked, "generated_inputs": generated,
            "source_snapshot_files": [{"path": "FixtureHost.csproj"}, {"path": "Program.cs"}],
            "compiler_input_identity": compiler_identity, "compiler_supplement_sha256": "b" * 64,
            "producer_identity": runtime_producer_identity(),
        }
        observed = RUNTIME_LAUNCHER.launch(request)
        self.assertEqual(observed["profile"], "local-storage")
        self.assertTrue(observed["process"]["intentional_abort_verified"])
        self.assertEqual(observed["capture"]["profile_input_state"], "empty")
        self.assertTrue(observed["capture"]["profile_input_matches"])
        self.assertEqual(observed["capture"]["interface_full_name"], "Demo.IStorage")
        self.assertEqual(observed["capture"]["observed_runtime_type"], "Demo.LocalStorage")
        self.assertTrue(observed["capture"]["host_disposed"])
        self.assertTrue(observed["capture"]["scope_disposed"])
        self.assertEqual(observed["capture"]["failure_code"], None)
        self.assertEqual(observed["termination"]["operation_nonce"], observed["operation_nonce"])
        self.assertEqual(observed["termination"]["process_id"], observed["capture"]["process_id"])
        self.assertTrue(observed["termination"]["intentional_host_abort"])
        loaded = observed["capture"]["loaded_assemblies"]
        hashed_loaded = observed["input_identity"]["loaded_runtime_assemblies"]
        self.assertTrue(loaded)
        self.assertEqual(len(loaded), len(hashed_loaded))
        self.assertTrue(all(isinstance(item["location"], str) for item in loaded))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in hashed_loaded))
        self.assertEqual({(item["identity"], item["location"]) for item in loaded},
                         {(item["identity"], item["location"]) for item in hashed_loaded})
        self.assertEqual(hashlib.sha256(json.dumps(observed["input_identity_projection"], ensure_ascii=True,
                                                    sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest(),
                         observed["input_sha256"])
        self.assertEqual(observed["input_identity"]["producer_identity"], request["producer_identity"])
        self.assertTrue((Path(observed["process"]["artifact_dir"]) / "input-identity.json").is_file())

    def test_runtime_receipts_are_associated_only_with_the_exact_compiler_candidate(self):
        interface_type = "Taggable.Api.Infrastructure.AdminTourManagement.ITourAssetStorage"
        local_type = "Taggable.Api.Infrastructure.AdminTourManagement.LocalDiskTourAssetStorage"
        cloud_type = "Taggable.Api.Infrastructure.AdminTourManagement.AzureBlobTourAssetStorage"

        def receipt(profile, candidate_id, candidate_type, observed_type):
            return {
                "binding": {"profile": profile, "interface_type_id": "interface-fact-1",
                            "interface_type": interface_type, "candidate_type_id": candidate_id,
                            "candidate_type": candidate_type},
                "capture": {"profile_input_key": "AdminTourManagement__Storage__TourImage__AccountName",
                            "profile_input_state": "empty" if profile == "local-storage" else "nonempty",
                            "selection_matches": True, "observed_runtime_type": observed_type,
                            "operation_nonce": "a" * 36, "process_id": 1234,
                            "host_disposed": True, "scope_disposed": True},
                "process": {"intentional_abort_verified": True},
                "input_sha256": "b" * 64,
            }

        observations = [
            receipt("local-storage", "local-fact-1", local_type, local_type),
            receipt("cloud-storage", "cloud-fact-1", cloud_type, cloud_type),
        ]
        local_edge = {"bound_interface_type_id": "interface-fact-1", "bound_interface_type": f"global::{interface_type}",
                      "candidate_type_id": "local-fact-1", "candidate_type": f"global::{local_type}"}
        cloud_edge = {**local_edge, "candidate_type_id": "cloud-fact-1", "candidate_type": f"global::{cloud_type}"}
        unrelated_edge = {**local_edge, "candidate_type_id": "unrelated-fact-1"}

        local_receipts = ATLAS._runtime_receipts_for_binding(local_edge, observations)
        cloud_receipts = ATLAS._runtime_receipts_for_binding(cloud_edge, observations)
        self.assertEqual([item["profile"] for item in local_receipts], ["local-storage"])
        self.assertEqual([item["profile"] for item in cloud_receipts], ["cloud-storage"])
        self.assertEqual(ATLAS._runtime_receipts_for_binding(unrelated_edge, observations), [])
        for summary in [*local_receipts, *cloud_receipts]:
            self.assertTrue(summary["selection_matches"])
            self.assertTrue(summary["host_and_scope_disposed"])
            self.assertFalse(summary["runtime_route_reachability_proven"])
            self.assertFalse(summary["runtime_DI_selection_proven"])

    @unittest.skipUnless(os.environ.get("ATLAS_DOTNET"), "runtime consumer fixture needs the approved local dotnet SDK")
    def test_runtime_index_and_consumers_keep_profile_receipts_source_candidate_scoped(self):
        project = self.repo / "FixtureHost.csproj"
        project.write_text('''<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings><AssemblyName>FixtureHost</AssemblyName></PropertyGroup>
</Project>
''', encoding="utf-8")
        (self.repo / "Program.cs").write_text('''using Fixture;
using Microsoft.Extensions.DependencyInjection;
using Taggable.Api.Infrastructure.AdminTourManagement;
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddScoped<IHandler<Request>, AssetHandler>();
if (!string.IsNullOrEmpty(builder.Configuration["AdminTourManagement:Storage:TourImage:AccountName"]))
    builder.Services.AddScoped<ITourAssetStorage, AzureBlobTourAssetStorage>();
else
    builder.Services.AddScoped<ITourAssetStorage, LocalDiskTourAssetStorage>();
var app = builder.Build();
app.MapControllers();
''', encoding="utf-8")
        (self.repo / "Storage.cs").write_text('''namespace Taggable.Api.Infrastructure.AdminTourManagement;
public interface ITourAssetStorage { string Read(); }
public sealed class LocalDiskTourAssetStorage : ITourAssetStorage { public string Read() => "local"; }
public sealed class AzureBlobTourAssetStorage : ITourAssetStorage { public string Read() => "cloud"; }
''', encoding="utf-8")
        (self.repo / "Api.cs").write_text('''using Microsoft.AspNetCore.Mvc;
using Taggable.Api.Infrastructure.AdminTourManagement;
namespace Fixture;
public sealed record Request;
public interface IHandler<T> { string Handle(T value); }
public sealed class AssetHandler(ITourAssetStorage storage) : IHandler<Request> {
    public string Handle(Request value) => storage.Read();
}
[ApiController]
[Route("api/assets")]
public sealed class AssetsController(IHandler<Request> handler) : ControllerBase
{
    [HttpGet("list")]
    public IActionResult Get() { handler.Handle(new Request()); return Ok(); }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "FixtureHost.csproj", "Program.cs", "Storage.cs", "Api.cs")
        empty_feed = self.root / "empty-runtime-feed"
        empty_feed.mkdir()
        nuget = self.root / "NuGet.Runtime.Config"
        nuget.write_text('<configuration><packageSources><clear/><add key="empty" value="'
                         + empty_feed.as_posix() + '"/></packageSources></configuration>', encoding="utf-8")
        dotnet = Path(os.environ["ATLAS_DOTNET"]).expanduser().resolve(strict=True)
        restore = subprocess.run([dotnet.as_posix(), "restore", project.as_posix(), "--configfile", nuget.as_posix(),
                                  "--ignore-failed-sources"], cwd=self.repo, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, timeout=60, check=False)
        self.assertEqual(restore.returncode, 0, restore.stderr or restore.stdout)
        snapshot = self.index()
        compiler = self.cli("compiler-index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db),
                            "--project", "FixtureHost.csproj", "--framework", "net8.0", expect=0)
        self.assertTrue(json.loads(compiler.stdout))
        current_graph = self.graph(snapshot["snapshot_id"])
        route = next(fact for fact in current_graph["facts"] if fact.get("kind") == "route_action"
                     and fact.get("route_literal") == "api/assets/list")

        index_args = ("runtime-index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db),
                      "--project", "FixtureHost.csproj", "--framework", "net8.0", "--interface",
                      "Taggable.Api.Infrastructure.AdminTourManagement.ITourAssetStorage", "--profile", "both")
        db_before_budget = self.db.read_bytes()
        limited = self.cli(*index_args, "--max-tokens", "1", expect=2)
        self.assertEqual(limited.stdout, "")
        self.assertIn("stdout withheld", limited.stderr)
        self.assertEqual(self.db.read_bytes(), db_before_budget)

        indexed = self.cli(*index_args, "--max-tokens", "65536", expect=0)
        runtime_document = json.loads(indexed.stdout)
        self.assertEqual({item["profile"] for item in runtime_document["observations"]},
                         {"local-storage", "cloud-storage"})
        self.assertFalse(runtime_document["runtime_route_reachability_proven"])
        self.assertFalse(runtime_document["runtime_DI_selection_proven"])
        by_candidate = {}
        for candidate, profile in (("LocalDiskTourAssetStorage", "local-storage"),
                                   ("AzureBlobTourAssetStorage", "cloud-storage")):
            impact = json.loads(self.impact(
                f"Taggable.Api.Infrastructure.AdminTourManagement.{candidate}.Read", max_tokens=65536).stdout)
            chains = impact.get("compiler_associated_route_paths", [])
            receipts = [receipt for path in chains for hop in path.get("call_chain", [])
                        for receipt in hop.get("runtime_startup_observations", [])]
            matching = [receipt for receipt in receipts if receipt["candidate_type"].endswith(candidate)]
            self.assertEqual({receipt["profile"] for receipt in matching}, {profile})
            by_candidate[f"Taggable.Api.Infrastructure.AdminTourManagement.{candidate}"] = {profile}
        packet = json.loads(self.evidence_pack(route["id"], max_tokens=65536).stdout)
        pack_receipts = packet["runtime_startup_candidate_evidence"]
        observed_pairs = {(item["candidate_type"], receipt["profile"])
                          for item in pack_receipts for receipt in item["runtime_startup_observations"]}
        self.assertEqual(observed_pairs,
                         {(candidate, profile) for candidate, profiles in by_candidate.items() for profile in profiles})
        self.assertFalse(packet["runtime_observation_scope"]["runtime_route_reachability_proven"])
        self.assertFalse(packet["runtime_observation_scope"]["runtime_DI_selection_proven"])

        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT profile,input_sha256,content_sha256,payload_json "
                                     "FROM atlas_runtime_observations ORDER BY profile LIMIT 1").fetchone()
            original = json.loads(row[3])
            tampered = json.loads(row[3])
            tampered["binding"]["candidate_type_id"] = "unrelated-source-type-id"
            encoded = ATLAS._canonical_json(tampered)
            content_hash = hashlib.sha256(encoded).hexdigest()
            connection.execute("UPDATE atlas_runtime_observations SET content_sha256=?,payload_json=? "
                               "WHERE profile=? AND input_sha256=?",
                               (content_hash, encoded.decode("ascii"), row[0], row[1]))
        db_after_tamper = self.db.read_bytes()
        for refused in (self.impact("Fixture.AssetHandler.Handle", max_tokens=65536, expect=2),
                        self.evidence_pack(route["id"], max_tokens=65536, expect=2)):
            self.assertEqual(refused.stdout, "")
            self.assertIn("runtime observation", refused.stderr)
            self.assertEqual(self.db.read_bytes(), db_after_tamper)

    def attach_compiler_fixture(self, snapshot, graph, route):
        """Attach synthetic mechanics evidence; this does not stand in for Roslyn proof."""
        import sys
        methods = [fact for fact in graph["facts"] if fact.get("kind") == "method_declaration"]
        action = next(fact for fact in methods if fact.get("method_name") == route["action_name"])
        implementation = next(fact for fact in methods if fact.get("method_name") == "Handle")
        injection = next(fact for fact in graph["facts"] if fact.get("kind") == "constructor_injection"
                         and fact.get("owner_type_id") == action.get("owner_type_id"))
        invocation = next(fact for fact in graph["facts"] if fact.get("kind") == "receiver_invocation_syntax"
                          and fact.get("method_id") == action["id"])
        registration = next(fact for fact in graph["facts"] if fact.get("kind") == "dependency_registration"
                            and fact.get("implementation_type_expression") == "Handler")
        reference_path = self.root / "compiler-reference.bin"
        reference_path.write_bytes(b"compiler reference fixture")
        project_path = self.repo / "Fixture.csproj"
        project_path.write_text("<Project />", encoding="utf-8")
        git(self.repo, "add", "--", "Fixture.csproj")
        assets = self.repo / "obj" / "project.assets.json"
        assets.parent.mkdir(parents=True, exist_ok=True)
        assets.write_text("{}", encoding="utf-8")
        flow_source = self.repo / "Flow.cs"
        flow_text = flow_source.read_text(encoding="utf-8")
        flow_source.write_text(flow_text.replace(
            "store.GetAsync();", "store.GetAsync(); System.Func<int, int> map = x => x + 1;", 1), encoding="utf-8")
        git(self.repo, "add", "--", "Flow.cs")
        snapshot = self.index()
        graph = self.graph(snapshot["snapshot_id"])
        route = next(fact for fact in graph["facts"] if fact.get("kind") == "route_action"
                     and fact.get("route_literal") == "api/customer/save")
        methods = [fact for fact in graph["facts"] if fact.get("kind") == "method_declaration"]
        action = next(fact for fact in methods if fact.get("method_name") == route["action_name"])
        implementation = next(fact for fact in methods if fact.get("method_name") == "Handle")
        injection = next(fact for fact in graph["facts"] if fact.get("kind") == "constructor_injection"
                         and fact.get("owner_type_id") == action.get("owner_type_id"))
        invocation = next(fact for fact in graph["facts"] if fact.get("kind") == "receiver_invocation_syntax"
                          and fact.get("method_id") == action["id"])
        registration = next(fact for fact in graph["facts"] if fact.get("kind") == "dependency_registration"
                            and fact.get("implementation_type_expression") == "Handler")
        generated = ATLAS._compiler_safe_tree(self.repo, "obj")
        reference = {"display": os.fspath(reference_path), "aliases": [], "embed_interop_types": False,
                     "kind": "Assembly", "sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest()}
        external_import = self.root / "external.targets"
        external_import.write_bytes(b"<Project />")
        import_logical = "external/external.targets"
        import_record = {"logical_path": import_logical, "path": external_import.as_posix(),
                         "sha256": hashlib.sha256(external_import.read_bytes()).hexdigest()}
        sdk_root = self.root / "sdk-fixture"
        build_host = sdk_root / "DotnetTools" / "dotnet-format" / "BuildHost-netcore"
        build_host.mkdir(parents=True)
        host_fixture = build_host / "host.dll"
        host_fixture.write_bytes(b"host fixture")
        toolchain = {"name": "fixture", "path": os.fspath(reference_path), "sha256": reference["sha256"]}
        lexical_manifest = ATLAS._compiler_lexical_method_manifest(snapshot, graph["extractor_identity"])
        inputs = {"lexical_method_manifest": lexical_manifest,
                  "lexical_method_manifest_sha256": hashlib.sha256(ATLAS._canonical_json(lexical_manifest)).hexdigest(),
                  "tracked_inputs": [{"logical_path": f"tracked/{entry['path']}", "path": entry["path"],
                                      "sha256": entry.get("sha256"), "size_bytes": entry.get("size_bytes"),
                                      "presence": entry.get("presence"), "type": entry.get("type"),
                                      "git_mode": entry.get("git_mode")} for entry in snapshot["files"]],
                  "generated_inputs": generated, "references": [reference], "imports": [import_record],
                  "toolchain_assemblies": [toolchain], "copied_tool_files": [],
                  "build_host_files": [{"path": "host.dll", "sha256": hashlib.sha256(host_fixture.read_bytes()).hexdigest()}],
                  "shipped_tool_inputs": ATLAS._compiler_shipped_tool_inputs(),
                  "dotnet_host": {"path": os.fspath(reference_path), "sha256": reference["sha256"]},
                  "project": "Fixture.csproj", "target_framework": "net10.0",
                  "sdk_path": sdk_root.as_posix(), "roslyn_version": "fixture", "language_version": "CSharp12",
                  "compilation_options": "fixture", "parse_options": "fixture"}
        call_span = invocation["source"]["span"]
        call_text = self.repo.joinpath(invocation["source"]["path"]).read_text(encoding="utf-8")
        call_offset = call_span["start_offset"]
        identifier_start = call_text.find("Handle", call_offset, call_span["end_offset"])
        call_source = {"path": invocation["source"]["path"], "sha256": invocation["source"]["sha256"],
                       "span": {**call_span, "start_offset": identifier_start,
                                "end_offset": identifier_start + len("Handle")}}
        relation = {"route": "api/customer/save", "http_method": "POST", "action_method": action["method_name"],
                    "service_type": injection["type_expression"], "bound_member": "IHandler.Handle",
                    "implementation_method": "global::Demo.Handler.Handle()", "action_source": action["source"],
                    "call_site_source": call_source, "service_parameter_source": injection["source"],
                    "bound_member_source": call_source, "implementation_source": implementation["source"],
                    "lexical_action_fact_id": action["id"], "lexical_implementation_fact_id": implementation["id"],
                    "lexical_route_fact_id": route["id"],
                    "implementation_type": "global::Demo.Handler", "implementation_method_containing_type": "global::Demo.Handler",
                    "compiler_implementation_match": True,
                    "registrations": [{"syntax": "services.AddScoped<IHandler, Handler>()", "source": registration["source"],
                                       "lexical_registration_fact_id": registration["id"],
                                       "runtime_DI_selection_proven": False}],
                    "runtime_DI_selection_proven": False}
        implementation_text = self.repo.joinpath(implementation["source"]["path"]).read_text(encoding="utf-8")
        helper = next(fact for fact in methods if fact.get("method_name") == "SaveAsync")
        root_id = ATLAS._source_call_node_id(implementation["source"])
        helper_id = ATLAS._source_call_node_id(helper["source"])
        invocation_start = implementation_text.index("store.SaveAsync()", implementation["source"]["span"]["start_offset"])
        graph_callsite = {"path": implementation["source"]["path"], "sha256": implementation["source"]["sha256"],
                          "span": {"start_offset": invocation_start, "end_offset": invocation_start + len("store.SaveAsync()"),
                                   "offset_unit": "unicode_codepoint"}}
        nested_start = implementation_text.index("x => x + 1", implementation["source"]["span"]["start_offset"])
        nested_source = {"path": implementation["source"]["path"], "sha256": implementation["source"]["sha256"],
                         "span": {"start_offset": nested_start, "end_offset": nested_start + len("x => x + 1"),
                                  "offset_unit": "unicode_codepoint"}}
        source_call_edge = {
            "route": relation["route"], "http_method": relation["http_method"],
            "route_fact_id": route["id"], "lexical_implementation_fact_id": implementation["id"],
            "implementation_type": relation["implementation_type"],
            "implementation_method": relation["implementation_method"],
            "caller_method": "global::Demo.Handler.Handle()", "callee_method": "global::Demo.Store.SaveAsync()", "dispatch_kind": "non_virtual_instance_source",
            "caller_lexical_method_fact_id": implementation["id"], "callee_lexical_method_fact_id": helper["id"],
            "caller_source": implementation["source"], "callee_source": helper["source"],
            "callee_containing_type": "global::Demo.Store", "call_site_source": graph_callsite, "compiler_binding_confirmed": True,
            "runtime_reachability_proven": False, "runtime_DI_selection_proven": False,
        }
        graph_caps = dict(ATLAS.SOURCE_CALL_GRAPH_CAPS)
        graph_counts = {"roots": 1, "nodes": 2, "edges": 1, "inspected_invocations": 1,
                        "unsupported": 0, "nested_body_exclusions": 1, "method_bodies_traversed": 2,
                        "serialized_graph_bytes": 1, "traversal_work": 1, "compatibility_records": 1,
                        "interface_candidate_checks": 0}
        graph_payload = {"schema_version": ATLAS.SOURCE_CALL_GRAPH_SCHEMA_VERSION, "status": "complete",
                         "caps": graph_caps, "counts": graph_counts,
                         "roots": [{"route": relation["route"], "http_method": relation["http_method"],
                                    "implementation_type": relation["implementation_type"],
                                    "implementation_method": relation["implementation_method"],
                                    "root_method": "global::Demo.Handler.Handle()", "root_node_id": root_id,
                                    "root_source": implementation["source"], "route_fact_id": route["id"],
                                    "lexical_implementation_method_fact_id": implementation["id"]}],
                         "nodes": [{"id": root_id, "method": "global::Demo.Handler.Handle()", "containing_type": "global::Demo.Handler",
                                    "source": implementation["source"], "lexical_method_fact_id": implementation["id"]},
                                   {"id": helper_id, "method": "global::Demo.Store.SaveAsync()", "containing_type": "global::Demo.Store",
                                    "source": helper["source"], "lexical_method_fact_id": helper["id"]}],
                         "edges": [{"caller_node_id": root_id, "callee_node_id": helper_id,
                                    "caller_method": "global::Demo.Handler.Handle()", "caller_source": implementation["source"],
                                    "callee_method": "global::Demo.Store.SaveAsync()", "callee_containing_type": "global::Demo.Store",
                                    "callee_source": helper["source"], "call_site_source": graph_callsite,
                                    "dispatch_kind": "non_virtual_instance_source", "compiler_binding_confirmed": True,
                                    "runtime_reachability_proven": False, "runtime_DI_selection_proven": False,
                                    "caller_lexical_method_fact_id": implementation["id"], "callee_lexical_method_fact_id": helper["id"]}],
                         "unsupported": [],
                         "nested_body_exclusions": [{"caller_node_id": root_id,
                             "caller_method": "global::Demo.Handler.Handle()", "caller_source": implementation["source"],
                             "nested_body_kind": "anonymous_function", "source": nested_source,
                             "reason": "synthetic verified lambda boundary"}]}
        for _ in range(4):
            graph_size = len(ATLAS._canonical_json(graph_payload))
            if graph_counts["serialized_graph_bytes"] == graph_size:
                break
            graph_counts["serialized_graph_bytes"] = graph_size
        payload = {"supplement_schema_version": 1,
                   "binding": {"snapshot_id": snapshot["snapshot_id"], "evidence_fingerprint": snapshot["evidence_fingerprint"],
                               "repository_root": self.repo.resolve().as_posix(), "extractor_identity": graph["extractor_identity"],
                               "project_path": "Fixture.csproj", "target_framework": "net10.0"},
                   "input_identity": inputs, "input_sha256": hashlib.sha256(ATLAS._canonical_json(inputs)).hexdigest(),
                   "provenance": {"sdk_path": "/sdk", "roslyn_version": "fixture", "language_version": "CSharp12",
                                  "target_framework": "net10.0", "source_trees": 1, "compiler_warnings": []},
                   "relationships": [relation], "unresolved": [], "source_call_graph": graph_payload,
                   "source_call_edges": [source_call_edge],
                   "source_call_unresolved": [], "runtime_DI_selection_proven": False}
        content_hash = hashlib.sha256(ATLAS._canonical_json(payload)).hexdigest()
        document = {**payload, "content_sha256": content_hash}
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS atlas_compiler_supplements (snapshot_id TEXT NOT NULL, project_path TEXT NOT NULL, content_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,project_path), FOREIGN KEY(snapshot_id) REFERENCES atlas_snapshots(snapshot_id))")
            connection.execute("INSERT INTO atlas_compiler_supplements VALUES (?,?,?,?)",
                               (snapshot["snapshot_id"], "Fixture.csproj", content_hash,
                                ATLAS._canonical_json(document).decode("ascii")))
        return reference_path, relation, snapshot, graph, route

    def test_impact_view_returns_verified_definition_and_exact_lexical_calls(self):
        source = self.repo / "Calls.cs"
        source.write_text('''namespace Demo;
class Target
{
    static void Work() { }
}
class Handler
{
    void First() { Target.Work(); /* Target.Work(); */ var text = "Target.Work()"; var value = $"{Target.Work()}"; }
    void Second() { Target.Work(); }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Calls.cs")
        self.index()

        result = self.impact("Target.Work")
        document = json.loads(result.stdout)
        self.assertEqual(document["result"], "impact_view")
        self.assertEqual(document["candidate_count"], 2)
        self.assertEqual([item["containing_method"] for item in document["invocation_candidates"]], ["Demo.Handler.First", "Demo.Handler.Second"])
        self.assertTrue(all(item["expression"] == "Target.Work(" for item in document["invocation_candidates"]))
        self.assertIn("static void Work()", document["definition"]["text"])
        self.assertEqual(document["budget"]["stdout_bytes_including_newline"], len(result.stdout.encode("ascii")))
        fully_qualified = json.loads(self.impact("Demo.Target.Work").stdout)
        self.assertEqual(fully_qualified["candidate_count"], 2)
        self.assertEqual(fully_qualified["invocation_candidates"], document["invocation_candidates"])

        refused = self.impact("Target.Work", max_tokens=100, expect=2)
        self.assertEqual(refused.stdout, "")
        self.assertIn("stdout withheld", refused.stderr)

    def test_compiler_supplement_consumers_validate_freshness_and_preserve_lexical_candidates(self):
        _initial, graph, route = self.evidence_fixture()
        reference, relation, _snapshot, _graph, current_route = self.attach_compiler_fixture(
            self.query(self.index()["snapshot_id"]), graph, route,
        )
        impact = json.loads(self.impact("Handler.Handle", max_tokens=100000).stdout)
        self.assertEqual(impact["candidate_count"], 0)
        callers = impact["compiler_confirmed_interface_callers"]
        self.assertEqual(len(callers), 1)
        self.assertEqual(callers[0]["route"], "api/customer/save")
        self.assertTrue(callers[0]["compiler_binding_confirmed"])
        self.assertFalse(callers[0]["runtime_DI_selection_proven"])
        self.assertFalse(callers[0]["registrations"][0]["runtime_DI_selection_proven"])

        packet = json.loads(self.evidence_pack(current_route["id"], max_tokens=100000).stdout)
        self.assertEqual(len(packet["compiler_relationships"]), 1)
        self.assertGreaterEqual(len(packet["compiler_source_snippets"]), 5)
        self.assertFalse(packet["compiler_relationship_semantics"]["runtime_DI_selection_proven"])
        budget_refusal = self.evidence_pack(current_route["id"], max_tokens=1000, expect=2)
        self.assertEqual(budget_refusal.stdout, "")
        self.assertIn("stdout withheld", budget_refusal.stderr)

        # A correctly rehashed receipt with an unapproved interface identity must be
        # rejected by both read-only consumers before either can render evidence.
        snapshot_row = self.query(self.index()["snapshot_id"])
        tampered_receipt = {
            "schema_version": ATLAS.RUNTIME_OBSERVATION_SCHEMA_VERSION,
            "kind": "runtime_startup_observation",
            "binding": {"snapshot_id": snapshot_row["snapshot_id"], "project_path": "Fixture.csproj",
                        "interface_type_id": "fixture-interface-id", "interface_type": "Demo.IStore",
                        "profile": "local-storage"},
            "profile_inputs": {}, "capture": {}, "termination": {}, "process": {},
            "input_identity": {}, "input_identity_projection": {}, "input_sha256": "a" * 64,
        }
        tampered_bytes = ATLAS._canonical_json(tampered_receipt)
        tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "CREATE TABLE atlas_runtime_observations (snapshot_id TEXT NOT NULL, project_path TEXT NOT NULL, "
                "interface_type_id TEXT NOT NULL, profile TEXT NOT NULL, input_sha256 TEXT NOT NULL, "
                "content_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, "
                "PRIMARY KEY(snapshot_id,project_path,interface_type_id,profile,input_sha256))")
            connection.execute(
                "INSERT INTO atlas_runtime_observations VALUES (?,?,?,?,?,?,?)",
                (snapshot_row["snapshot_id"], "Fixture.csproj", "fixture-interface-id", "local-storage",
                 "a" * 64, tampered_hash, tampered_bytes.decode("ascii")),
            )
        db_before_refusal = self.db.read_bytes()
        runtime_impact_refusal = self.impact("Handler.Handle", max_tokens=100000, expect=2)
        runtime_pack_refusal = self.evidence_pack(current_route["id"], max_tokens=100000, expect=2)
        for refused in (runtime_impact_refusal, runtime_pack_refusal):
            self.assertEqual(refused.stdout, "")
            self.assertIn("profile/interface combination is not approved", refused.stderr)
            self.assertEqual(self.db.read_bytes(), db_before_refusal)
        with sqlite3.connect(self.db) as connection:
            connection.execute("DROP TABLE atlas_runtime_observations")

        assets = self.repo / "obj" / "project.assets.json"
        original_assets = assets.read_bytes()
        assets.write_bytes(original_assets + b" ")
        stale_generated = self.impact("Handler.Handle", expect=2)
        self.assertIn("generated inputs are stale", stale_generated.stderr)
        assets.write_bytes(original_assets)

        original_reference = reference.read_bytes()
        reference.write_bytes(original_reference + b"changed")
        stale_reference = self.evidence_pack(current_route["id"], expect=2)
        self.assertIn("reference changed", stale_reference.stderr)
        reference.write_bytes(original_reference)

        external_import = self.root / "external.targets"
        original_import = external_import.read_bytes()
        external_import.write_bytes(original_import + b" changed")
        stale_import = self.impact("Handler.Handle", expect=2)
        self.assertIn("import changed or is missing", stale_import.stderr)
        external_import.write_bytes(original_import)

        host_fixture = self.root / "sdk-fixture" / "DotnetTools" / "dotnet-format" / "BuildHost-netcore" / "host.dll"
        original_host = host_fixture.read_bytes()
        host_fixture.write_bytes(original_host + b" changed")
        stale_host = self.impact("Handler.Handle", expect=2)
        self.assertIn("BuildHost file changed or is missing", stale_host.stderr)
        host_fixture.write_bytes(original_host)

        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_compiler_supplements WHERE snapshot_id=?",
                                     (_snapshot["snapshot_id"],)).fetchone()
            original_payload = json.loads(row[0])
        manifest_tamper = json.loads(json.dumps(original_payload))
        manifest_tamper["input_identity"]["lexical_method_manifest"]["methods"].pop()
        manifest_tamper["input_identity"]["lexical_method_manifest_sha256"] = hashlib.sha256(
            ATLAS._canonical_json(manifest_tamper["input_identity"]["lexical_method_manifest"])).hexdigest()
        manifest_tamper["input_sha256"] = hashlib.sha256(ATLAS._canonical_json(manifest_tamper["input_identity"])).hexdigest()
        manifest_stable = {key: value for key, value in manifest_tamper.items() if key != "content_sha256"}
        manifest_tamper["content_sha256"] = hashlib.sha256(ATLAS._canonical_json(manifest_stable)).hexdigest()
        manifest_bytes = ATLAS._canonical_json(manifest_tamper).decode("ascii")
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                               (manifest_tamper["content_sha256"], manifest_bytes, _snapshot["snapshot_id"]))
        manifest_refusal = self.impact("Handler.Handle", expect=2)
        self.assertEqual(manifest_refusal.stdout, "")
        self.assertIn("lexical method manifest is stale or corrupt", manifest_refusal.stderr)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                               (original_payload["content_sha256"], row[0], _snapshot["snapshot_id"]))
        mutations = [
            ("missing dispatch_kind", lambda edge: edge.pop("dispatch_kind"), False),
            ("invalid dispatch_kind", lambda edge: edge.update(dispatch_kind="virtual_instance_source"), False),
            ("list dispatch_kind on unrelated edge", lambda edge: edge.update(dispatch_kind=[]), True),
            ("dict dispatch_kind on unrelated edge", lambda edge: edge.update(dispatch_kind={}), True),
            ("missing DI label", lambda edge: edge.pop("runtime_DI_selection_proven"), False),
            ("true DI label", lambda edge: edge.update(runtime_DI_selection_proven=True), False),
        ]
        for label, mutate, unrelated in mutations:
            tampered = json.loads(json.dumps(original_payload))
            edge = tampered["source_call_edges"][0]
            mutate(edge)
            if unrelated:
                edge["callee_lexical_method_fact_id"] = "unrelated-saved-method-fact"
            stable = {key: value for key, value in tampered.items() if key != "content_sha256"}
            tampered["content_sha256"] = hashlib.sha256(ATLAS._canonical_json(stable)).hexdigest()
            payload_json = ATLAS._canonical_json(tampered).decode("ascii")
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                                   (tampered["content_sha256"], payload_json, _snapshot["snapshot_id"]))
            db_before_refusal = self.db.read_bytes()
            refused = self.impact("Handler.Handle", expect=2)
            self.assertEqual(refused.stdout, "", label)
            self.assertIn("compiler", refused.stderr, label)
            self.assertEqual(self.db.read_bytes(), db_before_refusal, label)
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                                   (original_payload["content_sha256"], row[0], _snapshot["snapshot_id"]))

        def reseal_graph_payload(tampered):
            graph_value = tampered["source_call_graph"]
            for _ in range(4):
                actual_size = len(ATLAS._canonical_json(graph_value))
                if graph_value["counts"]["serialized_graph_bytes"] == actual_size:
                    break
                graph_value["counts"]["serialized_graph_bytes"] = actual_size
            stable_value = {key: value for key, value in tampered.items() if key != "content_sha256"}
            tampered["content_sha256"] = hashlib.sha256(ATLAS._canonical_json(stable_value)).hexdigest()
            return ATLAS._canonical_json(tampered).decode("ascii")

        disconnected_fact = next(fact for fact in graph["facts"] if fact.get("kind") == "method_declaration"
                                 and fact.get("method_name") == "GetAsync")
        graph_node_id = ATLAS._source_call_node_id(disconnected_fact["source"])
        graph_tampers = [
            ("boolean version", lambda g: g.update(schema_version=True)),
            ("float cap", lambda g: g["caps"].update(roots=float(ATLAS.SOURCE_CALL_GRAPH_CAPS["roots"]))),
            ("invented owner", lambda g: g["nodes"][0].update(containing_type="global::Invented.Owner")),
            ("invented edge owner", lambda g: g["edges"][0].update(callee_containing_type="global::Invented.Owner")),
            ("disconnected node", lambda g: (g["nodes"].append({"id": graph_node_id,
                "method": "global::Demo.Store.GetAsync()", "containing_type": "global::Demo.Store",
                "source": disconnected_fact["source"], "lexical_method_fact_id": disconnected_fact["id"]}),
                g["counts"].update(nodes=g["counts"]["nodes"] + 1,
                                   method_bodies_traversed=g["counts"]["method_bodies_traversed"] + 1))),
            ("missing endpoint", lambda g: g["edges"][0].update(callee_node_id="missing-node")),
            ("root identity", lambda g: g["roots"][0].update(route="api/other")),
            ("traversal cap", lambda g: g["counts"].update(traversal_work=ATLAS.SOURCE_CALL_GRAPH_CAPS["traversal_work"] + 1)),
            ("unsupported kind and reason", lambda g: (
                g["unsupported"].append({"caller_node_id": g["roots"][0]["root_node_id"],
                    "caller_method": g["roots"][0]["root_method"], "caller_source": g["roots"][0]["root_source"],
                    "call_site_source": g["roots"][0]["root_source"], "kind": [], "reason": {}}),
                g["counts"].update(unsupported=g["counts"]["unsupported"] + 1,
                    inspected_invocations=g["counts"]["inspected_invocations"] + 1,
                    traversal_work=g["counts"]["traversal_work"] + 1,
                    compatibility_records=g["counts"]["compatibility_records"] + 1))),
            ("unsupported reason type", lambda g: (
                g["unsupported"].append({"caller_node_id": g["roots"][0]["root_node_id"],
                    "caller_method": g["roots"][0]["root_method"], "caller_source": g["roots"][0]["root_source"],
                    "call_site_source": g["edges"][0]["call_site_source"],
                    "kind": "unsupported_source_call", "reason": {}}),
                g["counts"].update(unsupported=g["counts"]["unsupported"] + 1,
                    inspected_invocations=g["counts"]["inspected_invocations"] + 1,
                    traversal_work=g["counts"]["traversal_work"] + 1,
                    compatibility_records=g["counts"]["compatibility_records"] + 1))),
            ("unexpected callee method only", lambda g: (
                g["unsupported"].append({"caller_node_id": g["roots"][0]["root_node_id"],
                    "caller_method": g["roots"][0]["root_method"], "caller_source": g["roots"][0]["root_source"],
                    "call_site_source": g["edges"][0]["call_site_source"],
                    "kind": "unsupported_source_call", "reason": "unsupported call", "callee_method": "unexpected"}),
                g["counts"].update(unsupported=g["counts"]["unsupported"] + 1,
                    inspected_invocations=g["counts"]["inspected_invocations"] + 1,
                    traversal_work=g["counts"]["traversal_work"] + 1,
                    compatibility_records=g["counts"]["compatibility_records"] + 1))),
            ("unexpected callee source only", lambda g: (
                g["unsupported"].append({"caller_node_id": g["roots"][0]["root_node_id"],
                    "caller_method": g["roots"][0]["root_method"], "caller_source": g["roots"][0]["root_source"],
                    "call_site_source": g["edges"][0]["call_site_source"],
                    "kind": "unsupported_source_call", "reason": "unsupported call",
                    "callee_source": g["edges"][0]["callee_source"]}),
                g["counts"].update(unsupported=g["counts"]["unsupported"] + 1,
                    inspected_invocations=g["counts"]["inspected_invocations"] + 1,
                    traversal_work=g["counts"]["traversal_work"] + 1,
                    compatibility_records=g["counts"]["compatibility_records"] + 1))),
            ("duplicate unsupported boundary", lambda g: (
                g["unsupported"].extend([{"caller_node_id": g["roots"][0]["root_node_id"],
                    "caller_method": g["roots"][0]["root_method"], "caller_source": g["roots"][0]["root_source"],
                    "call_site_source": g["edges"][0]["call_site_source"],
                    "kind": "unsupported_source_call", "reason": "unsupported call"}] * 2),
                g["counts"].update(unsupported=g["counts"]["unsupported"] + 2,
                    inspected_invocations=g["counts"]["inspected_invocations"] + 2,
                    traversal_work=g["counts"]["traversal_work"] + 2,
                    compatibility_records=g["counts"]["compatibility_records"] + 2))),
            ("nested kind", lambda g: g["nested_body_exclusions"][0].update(nested_body_kind=[])),
            ("nested reason type", lambda g: g["nested_body_exclusions"][0].update(reason={})),
            ("duplicate nested boundary", lambda g: (g["nested_body_exclusions"].append(
                json.loads(json.dumps(g["nested_body_exclusions"][0]))),
                g["counts"].update(nested_body_exclusions=g["counts"]["nested_body_exclusions"] + 1))),
            ("callsite token", lambda g: g["edges"][0]["call_site_source"]["span"].update(
                start_offset=self.repo.joinpath("Flow.cs").read_text(encoding="utf-8").index("store.GetAsync()"),
                end_offset=self.repo.joinpath("Flow.cs").read_text(encoding="utf-8").index("store.GetAsync()") + len("store.GetAsync()"))),
        ]
        for label, mutate in graph_tampers:
            tampered = json.loads(json.dumps(original_payload))
            mutate(tampered["source_call_graph"])
            encoded = reseal_graph_payload(tampered)
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                                   (tampered["content_sha256"], encoded, _snapshot["snapshot_id"]))
            db_before_refusal = self.db.read_bytes()
            impact_refused = self.impact("Handler.Handle", expect=2)
            pack_refused = self.evidence_pack(current_route["id"], expect=2)
            self.assertEqual(impact_refused.stdout, "", label)
            self.assertEqual(pack_refused.stdout, "", label)
            self.assertEqual(self.db.read_bytes(), db_before_refusal, label)
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                                   (original_payload["content_sha256"], row[0], _snapshot["snapshot_id"]))

        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_compiler_supplements WHERE snapshot_id=?",
                                     (_snapshot["snapshot_id"],)).fetchone()
            tampered = json.loads(row[0])
            tampered["content_sha256"] = "0" * 64
            connection.execute("UPDATE atlas_compiler_supplements SET payload_json=? WHERE snapshot_id=?",
                               (json.dumps(tampered), _snapshot["snapshot_id"]))
        corrupted = self.impact("Handler.Handle", expect=2)
        self.assertIn("content hash mismatch", corrupted.stderr)

    def test_compiler_index_refusal_does_not_write_for_an_untracked_project(self):
        self.evidence_fixture()
        before = self.db.read_bytes()
        refused = self.cli("compiler-index", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--project", "missing.csproj", "--framework", "net10.0", expect=2)
        self.assertIn("must match exactly one current tracked file", refused.stderr)
        self.assertEqual(self.db.read_bytes(), before)

    def test_captured_generic_call_edge_is_not_bindable_to_saved_lexical_fact(self):
        # Exact reduced records from atlas-real-source-call-validator-input.json
        # (SHA-256 5cd76ef93138f034dea0456135f5424c6c703feacdfc5aa2e382bdb8299e1272),
        # edge 21. This preserves the actual rejection boundary: the compiler
        # edge points at EncryptPayload<T>, while the saved lexical graph has no
        # matching method declaration fact for that generic declaration.
        source_path = "src/Taggable.Api/Application/AdminTourManagement/AdminTourManagementHandlers.cs"
        source_hash = "fc55fea4b5547d7513ee259385d3477162ddae209d70a9004b26255f6a5a7225"
        callee_path = "src/Taggable.Api/Infrastructure/LegacyInterop/LegacyPayloadEncryption.cs"
        callee_hash = "e04c76c9c19bab4de17d94d4a530f951275c4d0c52a021ded91da4f1faa4888d"

        def anchor(path, digest, start, end):
            return {"path": path, "sha256": digest,
                    "span": {"start_offset": start, "end_offset": end}}

        edge = {
            "route": "api/admin/generateTvSlideshowUrl", "http_method": "POST",
            "implementation_type": "global::Taggable.Api.Application.AdminTourManagement.GenerateAdminTvSlideshowUrlQueryHandler",
            "implementation_method": "Handle", "caller_method": "Handle",
            "caller_source": anchor(source_path, source_hash, 10877, 11770),
            "callee_method": "EncryptPayload<global::System.Collections.Generic.Dictionary<string, long>>",
            "callee_containing_type": "global::Taggable.Api.Infrastructure.LegacyInterop.LegacyPayloadEncryption",
            "callee_source": anchor(callee_path, callee_hash, 416, 1044),
            "call_site_source": anchor(source_path, source_hash, 11317, 11444),
            "dispatch_kind": "static_source",
            "compiler_binding_confirmed": True, "runtime_reachability_proven": False,
            "runtime_DI_selection_proven": False,
        }
        caller_fact = {
            "id": "38d4276fd03752b3943e083b", "kind": "method_declaration",
            "method_name": "Handle",
            "owner_type_id": "Taggable.Api.Application.AdminTourManagement.GenerateAdminTvSlideshowUrlQueryHandler`0",
            "source": anchor(source_path, source_hash, 10877, 11770),
        }
        snapshot = {
            "files": [
                {"path": source_path, "presence": "present", "type": "file", "sha256": source_hash},
                {"path": callee_path, "presence": "present", "type": "file", "sha256": callee_hash},
            ],
            "source_graph": {"facts": [caller_fact]},
        }
        relationship = {
            "route": edge["route"], "http_method": edge["http_method"],
            "implementation_type": edge["implementation_type"],
            "implementation_method": edge["implementation_method"],
            "lexical_implementation_fact_id": caller_fact["id"],
            "lexical_route_fact_id": "a26a4828bf903d02679f0420",
        }
        with self.assertRaisesRegex(ATLAS.AtlasError, "callee anchor does not identify exactly one saved lexical method fact: matches=0"):
            ATLAS._verify_compiler_source_call_edges(snapshot, [relationship], [edge])

        missing_dispatch = dict(edge)
        missing_dispatch.pop("dispatch_kind")
        with self.assertRaisesRegex(ATLAS.AtlasError, "missing or invalid dispatch_kind"):
            ATLAS._verify_compiler_source_call_edges(snapshot, [relationship], [missing_dispatch])
        invalid_dispatch = {**edge, "dispatch_kind": "virtual_instance_source"}
        with self.assertRaisesRegex(ATLAS.AtlasError, "missing or invalid dispatch_kind"):
            ATLAS._verify_compiler_source_call_edges(snapshot, [relationship], [invalid_dispatch])

    def test_source_call_limitations_require_one_exact_handler_relationship(self):
        digest = "a" * 64
        relationship = {"route": "api/items/one", "http_method": "GET",
                        "implementation_type": "global::Fixture.First", "implementation_method": "Handle"}
        record = {**relationship, "kind": "unsupported_handler_source_call", "reason": "unsupported shape",
                  "source": {"path": "Fixture.cs", "sha256": digest,
                             "span": {"start_offset": 3, "end_offset": 9}}}
        snapshot = {"files": [{"path": "Fixture.cs", "presence": "present", "type": "file", "sha256": digest}]}
        verified = ATLAS._verify_compiler_source_call_unresolved(snapshot, [relationship], [record])
        self.assertEqual(verified[0]["route"], "api/items/one")

        missing_identity = dict(record)
        missing_identity.pop("route")
        with self.assertRaisesRegex(ATLAS.AtlasError, "limitation has invalid route"):
            ATLAS._verify_compiler_source_call_unresolved(snapshot, [relationship], [missing_identity])

        wrong_identity = {**record, "route": "api/items/two"}
        with self.assertRaisesRegex(ATLAS.AtlasError, "matches=0 route='api/items/two'"):
            ATLAS._verify_compiler_source_call_unresolved(snapshot, [relationship], [wrong_identity])

        duplicate_relationships = [relationship, dict(relationship)]
        with self.assertRaisesRegex(ATLAS.AtlasError, "matches=2 route='api/items/one'"):
            ATLAS._verify_compiler_source_call_unresolved(snapshot, duplicate_relationships, [record])

    @unittest.skipUnless(os.environ.get("ATLAS_DOTNET"), "real Roslyn fixture needs the approved local dotnet SDK")
    def test_compiler_index_real_roslyn_routes_and_multiple_implementations(self):
        project = self.repo / "Fixture.csproj"
        project.write_text('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings></PropertyGroup>
  <ItemGroup><FrameworkReference Include="Microsoft.AspNetCore.App" /></ItemGroup>
</Project>
''', encoding="utf-8")
        source = self.repo / "Fixture.cs"
        source.write_text('''using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
namespace Fixture;
public sealed record Request(int Number = 0);
public readonly record struct ResolvedAssociation(long LocationId, long TourTimeSlotsId, string GroupId,
    string? Name, DateTime? MediaCreatedAt, long? UploadedByDeviceId = null, string? StablePhotoId = null);
public interface IHandler<T> { string Handle(T value); }
public static class Support
{
    public static string Load(Request value) => "loaded";
    public static string Load(string value) => value;
    public static string Convert<T>(T value) => value.ToString()!;
    public static string Deferred(Request value) => value.ToString();
    public static System.Threading.Tasks.Task<Request?> WorkerHelper(Request value) => null!;
    public static System.Threading.Tasks.Task<IReadOnlyList<long>> SearchHelper(string query,
        IReadOnlyList<(long ImageId, string S3Key)> images, CancellationToken cancellationToken) => null!;
    public static System.Threading.Tasks.Task<ResolvedAssociation> ResolveHelper(ResolvedAssociation value) => null!;
    public static string DeepStart(Request value) => DeepLeft(value) + DeepRight(value);
    public static string DeepLeft(Request value) => DeepMiddle(value);
    public static string DeepRight(Request value) => DeepMiddle(value);
    public static string DeepMiddle(Request value) => DeepLeaf(value);
    public static string DeepLeaf(Request value) => DeepMiddle(value) + PartialSupport<string, int>.Touch(value);
    public static string ProjectTrend(Request value) => Array.Empty<Request>().Select(_ => { decimal Money(decimal amount) => amount; return Money(1m).ToString(); }).FirstOrDefault() ?? value.ToString();
}
public static partial class PartialSupport<T, U>
{
    public static string Touch(Request value) => value.ToString();
}
public static partial class PartialSupport<T, U> { }
public static class FixtureExtensions { public static string Extend(this Request value) => value.ToString(); }
public sealed class AccessGate
{
    public bool Check(Request value) => true;
    public bool Check(string value) => true;
}
public class AuditTrail { public string Record(Request value) => value.ToString(); }
public interface IWorker { System.Threading.Tasks.Task<Request?> Run(Request value); }
public interface IFaceSearchProcessor
{
    System.Threading.Tasks.Task<IReadOnlyList<long>> SearchAsync(string query,
        IReadOnlyList<(long ImageId, string S3Key)> images, CancellationToken cancellationToken);
}
public interface IAssociationResolver
{
    System.Threading.Tasks.Task<ResolvedAssociation> ResolveAsync(ResolvedAssociation value);
}
public interface IWorkerBase { string RunChild(Request value); }
public interface IChildWorker : IWorkerBase { }
public interface IGenericWorker<T> { string RunGeneric(Request value); }
public class VirtualWorker : IWorker { public virtual System.Threading.Tasks.Task<Request?> Run(Request value) => null!; }
public sealed class ChildWorker : IChildWorker { public string RunChild(Request value) => value.ToString(); }
public sealed class GenericWorker<T> : IGenericWorker<T> { public string RunGeneric(Request value) => value.ToString(); }
public class ConcreteWorker : IWorker, IFaceSearchProcessor, IAssociationResolver
{
    public System.Threading.Tasks.Task<Request?> Run(Request value) => Support.WorkerHelper(value);
    public System.Threading.Tasks.Task<IReadOnlyList<long>> SearchAsync(string query,
        IReadOnlyList<(long ImageId, string S3Key)> images, CancellationToken cancellationToken) =>
        Support.SearchHelper(query, images, cancellationToken);
    public System.Threading.Tasks.Task<ResolvedAssociation> ResolveAsync(ResolvedAssociation value) =>
        Support.ResolveHelper(value);
}
public sealed class InheritedWorker : ConcreteWorker { }
public sealed class First(AccessGate gate, IWorker interfaceWorker, VirtualWorker virtualWorker,
    IFaceSearchProcessor faceSearch, IAssociationResolver associationResolver,
    IChildWorker childWorker, IGenericWorker<Request> genericWorker) : IHandler<Request>
{
    public string Handle(Request value)
    {
        var loaded = Support.Load(value) + Support.Deferred(value) + Support.DeepStart(value) + Support.ProjectTrend(value);
        _ = gate.Check(value);
            IReadOnlyList<(long ImageId, string S3Key)> imagePairs =
                new (long ImageId, string S3Key)[] { ((long)value.Number, "key") };
            _ = interfaceWorker.Run(value);
            _ = faceSearch.SearchAsync("query", imagePairs, default);
            _ = associationResolver.ResolveAsync(default);
                _ = childWorker.RunChild(value);
            _ = genericWorker.RunGeneric(value);
        _ = virtualWorker.Run(value);
        _ = Support.Convert(value);
        _ = System.Linq.Enumerable.Empty<Request>();
        _ = value.Extend();
        _ = FixtureExtensions.Extend(value);
        string Local(Request input) => Support.Load(input);
        Func<Request, string> deferred = input => Support.Load(input);
        Func<Request, string> deferredAgain = input => Support.Deferred(input);
        return loaded;
    }
}
public sealed class Second(AuditTrail trail) : IHandler<Request>
{
    public string Handle(Request value) => Support.Load(value) + Support.Deferred(value) + Support.DeepStart(value) + Support.ProjectTrend(value)
        + trail.Record(value)
        + ((Func<Request, string>)(input => Support.Load(input)))(value);
}
public class BaseHandler : IHandler<Request> { public string Handle(Request value) => Support.DeepStart(value) + Support.ProjectTrend(value); }
public sealed class Inherited : BaseHandler { }
public sealed class Idle : IHandler<Request> { public string Handle(Request value) => "idle"; }
[ApiController]
[Route("api/items")]
public sealed class ItemsController(IHandler<Request> handler) : ControllerBase
{
    [HttpGet("one")]
    [HttpPost("two")]
    public IActionResult Relative(Request value) { handler.Handle(value); return Ok(); }
    [HttpGet("/absolute")]
    public IActionResult Absolute(Request value) { handler.Handle(value); return Ok(); }
    [HttpGet("~/tilde")]
    public IActionResult Tilde(Request value) { handler.Handle(value); return Ok(); }
}
public static class Registrations
{
    public static void Add(IServiceCollection services)
    {
            services.AddScoped<IHandler<Request>, First>();
            services.AddScoped<IHandler<Request>, Second>();
            services.AddScoped<IHandler<Request>, BaseHandler>();
            services.AddScoped<IHandler<Request>, Inherited>();
            services.AddScoped<IHandler<Request>, Idle>();
            services.AddScoped<IHandler<Request>, First>();
            services.AddScoped<AccessGate>();
            services.AddScoped<AuditTrail>();
            services.AddScoped<IWorker, VirtualWorker>();
    }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Fixture.csproj", "Fixture.cs")
        empty_feed = self.root / "empty-feed"
        empty_feed.mkdir()
        nuget = self.root / "NuGet.Config"
        nuget.write_text(f'<configuration><packageSources><clear/><add key="empty" value="{empty_feed}"/></packageSources></configuration>', encoding="utf-8")
        restore = subprocess.run([os.environ["ATLAS_DOTNET"], "restore", os.fspath(project), "--configfile", os.fspath(nuget), "--ignore-failed-sources"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(restore.returncode, 0, restore.stderr or restore.stdout)
        generated_before = ATLAS._compiler_safe_tree(self.repo, "obj")
        snapshot = self.index()
        indexed = self.cli("compiler-index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db),
                           "--project", "Fixture.csproj", "--framework", "net8.0")
        self.assertEqual(indexed.returncode, 0, indexed.stderr)
        with sqlite3.connect(self.db) as connection:
            raw = connection.execute("SELECT payload_json FROM atlas_compiler_supplements WHERE snapshot_id=?", (snapshot["snapshot_id"],)).fetchone()[0]
        payload = json.loads(raw)
        relationships = payload["relationships"]
        by_route = {}
        for relation in relationships:
            by_route.setdefault((relation["http_method"], relation["route"]), []).append(relation)
        expected = {("GET", "api/items/one"), ("POST", "api/items/two"), ("GET", "absolute"), ("GET", "tilde")}
        self.assertEqual(set(by_route), expected)
        for route_relations in by_route.values():
            self.assertEqual({relation["implementation_type"] for relation in route_relations},
                             {"global::Fixture.First", "global::Fixture.Second", "global::Fixture.BaseHandler",
                              "global::Fixture.Inherited", "global::Fixture.Idle"})
            self.assertEqual(len({relation["lexical_route_fact_id"] for relation in route_relations}), 1)
            for relation in route_relations:
                self.assertEqual({item["implementation_type"] for item in relation["registrations"]}, {relation["implementation_type"]})
                self.assertEqual(len(relation["registrations"]), 2 if relation["implementation_type"] == "global::Fixture.First" else 1)
        self.assertIsInstance(payload["input_identity"]["compilation_options"], dict)
        parse_options = payload["input_identity"]["parse_options"]
        self.assertTrue(parse_options and all({"language_version", "preprocessor_symbols", "features"} <= set(item) for item in parse_options))
        imports = payload["input_identity"]["imports"]
        self.assertTrue(any("Microsoft.NET.Sdk" in item["path"] and item["path"].endswith("Sdk.props") for item in imports), imports)
        self.assertTrue(any(item["path"] == "Microsoft.CodeAnalysis.Workspaces.MSBuild.BuildHost.dll"
                            for item in payload["input_identity"]["build_host_files"]))
        self.assertEqual({item["logical_path"] for item in payload["input_identity"]["shipped_tool_inputs"]},
                         {"atlas-compiler/WorkspaceProgram.cs", "atlas-compiler/extractor.csproj"})
        self.assertIn("Microsoft.CodeAnalysis.CSharp", {item["name"] for item in payload["input_identity"]["toolchain_assemblies"]})
        self.assertTrue(any(item["logical_path"] == "Microsoft.CodeAnalysis.CSharp.dll"
                            for item in payload["input_identity"]["copied_tool_files"]))
        self.assertTrue(any(item["logical_path"].startswith("external/Users/kamenkamenov/.dotnet/sdk/")
                            and "/Sdks/Microsoft.NET.Sdk/targets/Microsoft.NET.Sdk.targets" in item["logical_path"]
                            for item in imports), imports)
        self.assertEqual(ATLAS._compiler_safe_tree(self.repo, "obj"), generated_before)
        self.assertFalse((self.repo / "bin").exists())
        source_edges = payload["source_call_edges"]
        self.assertEqual(len(source_edges), 64)
        self.assertEqual({edge["callee_method"] for edge in source_edges},
                         {"Load", "Deferred", "DeepStart", "Check", "Record", "Run", "SearchAsync", "ResolveAsync"})
        self.assertEqual({edge["dispatch_kind"] for edge in source_edges},
                         {"static_source", "non_virtual_instance_source", "interface_implementation_source"})
        static_edges = [edge for edge in source_edges if edge["dispatch_kind"] == "static_source"]
        instance_edges = [edge for edge in source_edges if edge["dispatch_kind"] == "non_virtual_instance_source"]
        self.assertEqual(len(static_edges), 32)
        self.assertEqual(len(instance_edges), 8)
        interface_edges = [edge for edge in source_edges if edge["dispatch_kind"] == "interface_implementation_source"]
        self.assertEqual(len(interface_edges), 24)
        self.assertTrue(all(edge["interface_binding"]["compiler_implementation_match"]
                            and not edge["interface_binding"]["runtime_DI_selection_proven"] for edge in interface_edges))
        self.assertEqual({edge["interface_binding"]["candidate_type"] for edge in interface_edges},
                         {"global::Fixture.ConcreteWorker", "global::Fixture.InheritedWorker"})
        interface_graph_edges = [edge for edge in payload["source_call_graph"]["edges"]
                                 if edge["dispatch_kind"] == "interface_implementation_source"]
        self.assertEqual(len(interface_graph_edges), 6)
        self.assertEqual(len({edge["callee_node_id"] for edge in interface_graph_edges}), 3)
        inherited_candidate_edge = next(edge for edge in interface_graph_edges
                                        if edge["interface_binding"]["candidate_type"] == "global::Fixture.InheritedWorker")
        self.assertEqual(inherited_candidate_edge["interface_binding"]["candidate_to_implementation_owner_path"][0]["to_type_id"],
                         "Fixture.ConcreteWorker`0")
        self.assertEqual({edge["callee_containing_type"] for edge in static_edges}, {"global::Fixture.Support"})
        lexical_graph = self.graph(snapshot["snapshot_id"])
        resolved_association_facts = [fact for fact in lexical_graph["facts"]
                                      if fact.get("kind") == "type_declaration"
                                      and fact.get("type_id") == "Fixture.ResolvedAssociation`0"]
        self.assertEqual(len(resolved_association_facts), 2)
        resolved_spans = [ATLAS._compiler_span(fact["source"]) for fact in resolved_association_facts]
        self.assertEqual(len({span[0] for span in resolved_spans}), 1)
        self.assertEqual(len({span[2] for span in resolved_spans}), 1)
        self.assertEqual(len({span[1] for span in resolved_spans}), 2)
        load_facts = [fact for fact in lexical_graph["facts"]
                      if fact.get("kind") == "method_declaration" and fact.get("method_name") == "Load"
                      and fact["source"]["path"] == "Fixture.cs"]
        self.assertEqual(len(load_facts), 2)
        expected_load = next(fact for fact in load_facts
                             if source.read_text(encoding="utf-8")[fact["source"]["span"]["start_offset"]:
                                                                 fact["source"]["span"]["end_offset"]]
                             == 'public static string Load(Request value) => "loaded";')
        load_edges = [edge for edge in source_edges if edge["callee_method"] == "Load"]
        self.assertEqual(len(load_edges), 8)
        self.assertEqual({edge["callee_lexical_method_fact_id"] for edge in load_edges}, {expected_load["id"]})
        self.assertTrue(all(edge["callee_source"] == expected_load["source"] for edge in load_edges))
        deferred_facts = [fact for fact in lexical_graph["facts"]
                          if fact.get("kind") == "method_declaration" and fact.get("method_name") == "Deferred"
                          and fact["source"]["path"] == "Fixture.cs"]
        deferred_edges = [edge for edge in source_edges if edge["callee_method"] == "Deferred"]
        self.assertEqual(len(deferred_facts), 1)
        self.assertEqual(len(deferred_edges), 8)
        self.assertEqual({edge["callee_lexical_method_fact_id"] for edge in deferred_edges}, {deferred_facts[0]["id"]})
        self.assertTrue(all(edge["callee_source"] == deferred_facts[0]["source"] for edge in deferred_edges))
        self.assertTrue(all(edge["compiler_binding_confirmed"] and not edge["runtime_reachability_proven"]
                            and not edge["runtime_DI_selection_proven"] for edge in source_edges))
        call_graph = payload["source_call_graph"]
        self.assertEqual(len(call_graph["roots"]), 20)
        idle_roots = [root for root in call_graph["roots"] if root["implementation_type"] == "global::Fixture.Idle"]
        self.assertEqual(len(idle_roots), 4)
        self.assertFalse(any(edge["caller_node_id"] == idle_roots[0]["root_node_id"] for edge in call_graph["edges"]))
        trend_fact = next(fact for fact in lexical_graph["facts"]
                          if fact.get("kind") == "method_declaration" and fact.get("method_name") == "ProjectTrend")
        trend_boundaries = [item for item in call_graph["unsupported"]
                            if item.get("kind") == "unsupported_lexical_source_method"]
        self.assertEqual(len(trend_boundaries), 3)
        self.assertTrue(all(".ProjectTrend(" in item["callee_method"]
                            and "Request" in item["callee_method"] for item in trend_boundaries),
                        [item["callee_method"] for item in trend_boundaries])
        self.assertTrue(all(ATLAS._compiler_span(item["callee_source"]) != ATLAS._compiler_span(trend_fact["source"])
                            for item in trend_boundaries))
        self.assertFalse(any(node["method"].endswith("ProjectTrend(Fixture.Request)") for node in call_graph["nodes"]))
        inherited_relations = [relation for relation in relationships if relation["implementation_type"] == "global::Fixture.Inherited"]
        self.assertEqual(len(inherited_relations), 4)
        self.assertTrue(all(relation["implementation_method_containing_type"] == "global::Fixture.BaseHandler"
                            for relation in inherited_relations))
        deep_leaf_matches = [node for node in call_graph["nodes"] if node["method"] == "DeepLeaf"]
        self.assertEqual(len(deep_leaf_matches), 1, [node["method"] for node in call_graph["nodes"]])
        deep_leaf = deep_leaf_matches[0]
        partial_type_facts = [fact for fact in lexical_graph["facts"]
                              if fact.get("kind") == "type_declaration" and fact.get("type_id") == "Fixture.PartialSupport`2"]
        self.assertEqual(len(partial_type_facts), 2)
        partial_helper_nodes = [node for node in call_graph["nodes"] if node["method"] == "Touch"]
        self.assertEqual(len(partial_helper_nodes), 1)
        self.assertEqual(partial_helper_nodes[0]["containing_type"], "global::Fixture.PartialSupport<T, U>")
        impact_deep = json.loads(self.impact("Support.DeepLeaf", max_tokens=100000).stdout)
        deep_paths = impact_deep["compiler_associated_route_paths"]
        self.assertEqual(len(deep_paths), 16)
        self.assertTrue(all(len(path["call_chain"]) == 4 for path in deep_paths))
        for path in deep_paths:
            chain = path["call_chain"]
            self.assertEqual(chain[0]["caller_lexical_method_fact_id"], path["handler"]["lexical_method_fact_id"])
            self.assertTrue(all(left["callee_lexical_method_fact_id"] == right["caller_lexical_method_fact_id"]
                                for left, right in zip(chain, chain[1:])))
            self.assertEqual(chain[-1]["callee_lexical_method_fact_id"], deep_leaf["lexical_method_fact_id"])
        interface_impact = json.loads(self.impact("Support.WorkerHelper", max_tokens=100000).stdout)
        interface_paths = interface_impact["compiler_associated_route_paths"]
        self.assertEqual(len(interface_paths), 4)
        self.assertTrue(all(path["hop_count"] == 2 for path in interface_paths))
        interface_hops = [path["call_chain"][0] for path in interface_paths]
        self.assertTrue(all(hop["dispatch_kind"] == "interface_implementation_source"
                            and hop["interface_binding"]["claim"] == "compiler_confirmed_source_interface_implementation_correspondence"
                            and not hop["interface_binding"]["runtime_DI_selection_proven"] for hop in interface_hops))
        self.assertEqual({hop["interface_binding"]["candidate_type"] for hop in interface_hops},
                         {"global::Fixture.ConcreteWorker"})
        self.assertEqual(call_graph["counts"]["nested_body_exclusions"], 4)
        check_facts = [fact for fact in lexical_graph["facts"]
                       if fact.get("kind") == "method_declaration" and fact.get("method_name") == "Check"
                       and fact["source"]["path"] == "Fixture.cs"]
        self.assertEqual(len(check_facts), 2)
        request_check = next(fact for fact in check_facts
                             if "Check(Request value)" in source.read_text(encoding="utf-8")
                             [fact["source"]["span"]["start_offset"]:fact["source"]["span"]["end_offset"]])
        check_edges = [edge for edge in instance_edges if edge["callee_method"] == "Check"]
        self.assertEqual(len(check_edges), 4)
        self.assertEqual({edge["callee_lexical_method_fact_id"] for edge in check_edges}, {request_check["id"]})
        self.assertTrue(all(edge["callee_source"] == request_check["source"] for edge in check_edges))
        self.assertEqual({edge["callee_containing_type"] for edge in check_edges}, {"global::Fixture.AccessGate"})
        record_facts = [fact for fact in lexical_graph["facts"]
                        if fact.get("kind") == "method_declaration" and fact.get("method_name") == "Record"
                        and fact["source"]["path"] == "Fixture.cs"]
        record_edges = [edge for edge in instance_edges if edge["callee_method"] == "Record"]
        self.assertEqual(len(record_facts), 1)
        self.assertEqual(len(record_edges), 4)
        self.assertEqual({edge["callee_lexical_method_fact_id"] for edge in record_edges}, {record_facts[0]["id"]})
        self.assertTrue(all(edge["callee_containing_type"] == "global::Fixture.AuditTrail" for edge in record_edges))
        self.assertTrue(all(edge["dispatch_kind"] == "non_virtual_instance_source" for edge in instance_edges))
        expression_handler_edges = [edge for edge in load_edges if edge["implementation_type"] == "global::Fixture.Second"]
        self.assertEqual(len(expression_handler_edges), 4)
        generic_limitations = [item for item in payload["source_call_unresolved"]
                               if item.get("reason") == "generic source method is outside the supported lexical source-call shape"]
        self.assertEqual(len(generic_limitations), 4)
        generic_identities = {(item["route"], item["http_method"], item["implementation_type"], item["implementation_method"])
                              for item in generic_limitations}
        self.assertEqual(len(generic_identities), 4)
        limitation_routes = {(item["http_method"], item["route"]) for item in generic_limitations}
        self.assertEqual(limitation_routes, expected)
        self.assertEqual({item["implementation_type"] for item in generic_limitations}, {"global::Fixture.First"})
        self.assertEqual({item["implementation_method"] for item in generic_limitations}, {"Handle"})
        checked_limitations = ATLAS._verify_compiler_source_call_unresolved(
            snapshot, relationships, payload["source_call_unresolved"])
        self.assertEqual(len(checked_limitations), len(payload["source_call_unresolved"]))
        external_call_offset = source.read_text(encoding="utf-8").index("System.Linq.Enumerable.Empty")
        external_generic_limitations = [item for item in payload["source_call_unresolved"]
                                        if item["source"]["span"]["start_offset"] == external_call_offset]
        self.assertEqual(len(external_generic_limitations), 4)
        self.assertTrue(all(item["reason"] == "bound call is outside the supported same-compilation static or non-virtual instance source-method shape"
                            for item in external_generic_limitations))
        virtual_limitations = [item for item in payload["source_call_unresolved"]
                               if item.get("source", {}).get("span", {}).get("start_offset") ==
                               source.read_text(encoding="utf-8").index("interfaceWorker.Run") or
                               item.get("source", {}).get("span", {}).get("start_offset") ==
                               source.read_text(encoding="utf-8").index("virtualWorker.Run")]
        self.assertEqual(len(virtual_limitations), 8)
        interface_limitations = [item for item in virtual_limitations if item["source"]["span"]["start_offset"] ==
                                 source.read_text(encoding="utf-8").index("interfaceWorker.Run")]
        self.assertEqual(len(interface_limitations), 4)
        self.assertTrue(all(item["kind"] == "unsupported_interface_candidate" for item in interface_limitations))
        self.assertEqual({item["interface_binding"]["candidate_type"] for item in interface_limitations},
                         {"global::Fixture.VirtualWorker"})
        direct_virtual_limitations = [item for item in virtual_limitations if item["source"]["span"]["start_offset"] ==
                                      source.read_text(encoding="utf-8").index("virtualWorker.Run")]
        self.assertTrue(all(item["kind"] == "unsupported_handler_source_call" for item in direct_virtual_limitations))
        inherited_interface_limits = [item for item in payload["source_call_unresolved"]
                                      if item["source"]["span"]["start_offset"] ==
                                      source.read_text(encoding="utf-8").index("childWorker.RunChild")]
        self.assertEqual(len(inherited_interface_limits), 4)
        self.assertTrue(all(item["kind"] == "unsupported_handler_source_call"
                            and "receiver interface different" in item["reason"] for item in inherited_interface_limits))
        generic_interface_limits = [item for item in payload["source_call_unresolved"]
                                    if item["source"]["span"]["start_offset"] ==
                                    source.read_text(encoding="utf-8").index("genericWorker.RunGeneric")]
        self.assertEqual(len(generic_interface_limits), 4)
        self.assertTrue(all(item["kind"] == "unsupported_handler_source_call"
                            and "generic" in item["reason"] for item in generic_interface_limits))
        extension_offsets = {source.read_text(encoding="utf-8").index("value.Extend()"),
                             source.read_text(encoding="utf-8").index("FixtureExtensions.Extend(value)")}
        extension_limitations = [item for item in payload["source_call_unresolved"]
                                 if item.get("source", {}).get("span", {}).get("start_offset") in extension_offsets]
        self.assertEqual(len(extension_limitations), 8)
        self.assertEqual({edge["route"] for edge in source_edges}, {route for _verb, route in expected})
        self.assertTrue(any(item["kind"] == "unsupported_handler_source_call" for item in payload["source_call_unresolved"]))
        impact = json.loads(self.impact("Support.Deferred", max_tokens=32000).stdout)
        self.assertEqual(impact["candidate_count"], 3)
        self.assertEqual(len(impact["compiler_associated_route_paths"]), 8)
        self.assertFalse(impact["compiler_associated_route_paths_scope"]["runtime_reachability_proven"])
        self.assertLessEqual(impact["budget"]["stdout_bytes_including_newline"], 32000)
        instance_impact = json.loads(self.impact("AuditTrail.Record", max_tokens=32000).stdout)
        self.assertEqual(len(instance_impact["compiler_associated_route_paths"]), 4)
        self.assertEqual({path["call"]["dispatch_kind"] for path in instance_impact["compiler_associated_route_paths"]},
                         {"non_virtual_instance_source"})
        self.assertFalse(instance_impact["compiler_associated_route_paths_scope"]["runtime_reachability_proven"])
        assets = self.repo / "obj" / "project.assets.json"
        original_assets = assets.read_bytes()
        assets.write_bytes(original_assets + b" ")
        stale = self.impact("Fixture.First.Handle", expect=2)
        self.assertIn("generated inputs are stale", stale.stderr)
        assets.write_bytes(original_assets)

        interface_groups = {}
        for edge in payload["source_call_graph"]["edges"]:
            if edge["dispatch_kind"] != "interface_implementation_source":
                continue
            call_span = ATLAS._compiler_span(edge["call_site_source"])
            interface_groups.setdefault((edge["caller_node_id"], call_span), []).append(edge)
        fixture_text_for_calls = source.read_text(encoding="utf-8")

        def candidate_group_at(call):
            expected_start = fixture_text_for_calls.index(call)
            return next(group for (_caller, span), group in interface_groups.items()
                        if span[1] == expected_start and len(group) == 2)

        positive_edges = candidate_group_at("interfaceWorker.Run")
        search_positive_edges = candidate_group_at("faceSearch.SearchAsync")
        association_positive_edges = candidate_group_at("associationResolver.ResolveAsync")
        for group in (positive_edges, search_positive_edges, association_positive_edges):
            self.assertEqual(len({edge["interface_binding"]["candidate_identity"] for edge in group}), 2)
            self.assertEqual(len({edge["callee_node_id"] for edge in group}), 1)
        self.assertEqual(len({edge["interface_binding"]["candidate_identity"] for edge in positive_edges}), 2)
        self.assertEqual(len({edge["callee_node_id"] for edge in positive_edges}), 1)
        self.assertEqual({edge["interface_binding"]["candidate_type"] for edge in positive_edges},
                         {"global::Fixture.ConcreteWorker", "global::Fixture.InheritedWorker"})
        positive = next(edge for edge in positive_edges
                        if edge["interface_binding"]["candidate_type"] == "global::Fixture.ConcreteWorker")
        inherited = next(edge for edge in positive_edges
                         if edge["interface_binding"]["candidate_type"] == "global::Fixture.InheritedWorker")
        search_positive = next(edge for edge in search_positive_edges
                               if edge["interface_binding"]["candidate_type"] == "global::Fixture.ConcreteWorker")
        association_positive = next(edge for edge in association_positive_edges
                                    if edge["interface_binding"]["candidate_type"] == "global::Fixture.ConcreteWorker")
        self.assertNotEqual(positive["interface_binding"]["candidate_to_implementation_owner_path"],
                            inherited["interface_binding"]["candidate_to_implementation_owner_path"])

        def make_anchor(template, start, end):
            anchor = json.loads(json.dumps(template))
            anchor["span"]["start_offset"] = start
            anchor["span"]["end_offset"] = end
            return anchor

        def reseal(tampered):
            graph_value = tampered["source_call_graph"]
            for _ in range(8):
                actual_size = len(ATLAS._canonical_json(graph_value))
                if graph_value["counts"]["serialized_graph_bytes"] == actual_size:
                    break
                graph_value["counts"]["serialized_graph_bytes"] = actual_size
            stable = {key: value for key, value in tampered.items() if key != "content_sha256"}
            tampered["content_sha256"] = hashlib.sha256(ATLAS._canonical_json(stable)).hexdigest()
            return ATLAS._canonical_json(tampered).decode("ascii")

        compiler_source = source.read_text(encoding="utf-8")
        binding = positive["interface_binding"]
        search_binding = search_positive["interface_binding"]
        association_binding = association_positive["interface_binding"]
        self.assertIn("Request?>", binding["bound_interface_signature"])
        self.assertIn("long ImageId", search_binding["bound_interface_signature"])
        self.assertIn("string S3Key", search_binding["bound_interface_signature"])
        self.assertIn("ImageId", search_binding["bound_interface_parameters"][1])
        self.assertIn("S3Key", search_binding["bound_interface_parameters"][1])
        self.assertIn("Task<global::Fixture.ResolvedAssociation>", association_binding["bound_interface_signature"])
        self.assertIn("string? Name", compiler_source)
        self.assertIn("DateTime? MediaCreatedAt", compiler_source)
        common_binding_keys = {
            "bound_interface_type", "bound_interface_type_id", "bound_interface_type_source",
            "bound_interface_declaration_source", "bound_interface_member", "bound_interface_signature",
            "bound_interface_parameters", "bound_interface_arity", "bound_interface_parameter_count",
            "bound_interface_member_source", "bound_interface_member_name_source", "candidate_type",
            "candidate_type_id", "candidate_type_source", "candidate_identity",
        }

        def candidate_edge(graph_value, identity, call_text=None):
            expected_start = compiler_source.index(call_text) if call_text else None
            return next(item for item in graph_value["edges"]
                        if isinstance(item.get("interface_binding"), dict)
                        and item["interface_binding"].get("candidate_identity") == identity
                        and (expected_start is None or
                             ATLAS._compiler_span(item.get("call_site_source"))[1] == expected_start))

        def make_exclusion(edge, native):
            source_binding = edge["interface_binding"]
            excluded_binding = {key: source_binding[key] for key in common_binding_keys}
            excluded_binding.update({"implementation_method": source_binding["implementation_method"],
                                     "implementation_method_source": source_binding["implementation_method_source"],
                                     "reason": native["interface_binding"]["reason"]})
            native.update({"caller_node_id": edge["caller_node_id"], "caller_method": edge["caller_method"],
                           "caller_source": edge["caller_source"], "call_site_source": edge["call_site_source"],
                           "interface_binding": excluded_binding})

        def conflict_with_supported_candidate(graph_value):
            edge = candidate_edge(graph_value, binding["candidate_identity"])
            unsupported = next(item for item in graph_value["unsupported"]
                               if item["kind"] == "unsupported_interface_candidate"
                               and item["caller_node_id"] == edge["caller_node_id"]
                               and ATLAS._compiler_span(item["call_site_source"]) ==
                               ATLAS._compiler_span(edge["call_site_source"]))
            make_exclusion(edge, unsupported)

        def wrong_overload_signature(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            proof = target["interface_binding"]
            proof["bound_interface_parameters"] = ["None:string"]
            proof["bound_interface_signature"] = replace_signature_parameter(
                proof["bound_interface_signature"], "None:string")
            proof["bound_interface_member"] = proof["bound_interface_type"] + "." + proof["bound_interface_signature"]

        def replace_signature_parameter(signature, parameter):
            member_name = signature.split("(", 1)[0]
            return_type = signature.rsplit(")->", 1)[1]
            return f"{member_name}({parameter})->{return_type}"

        def wrong_signature_parameters_disagree(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            proof = target["interface_binding"]
            proof["bound_interface_signature"] = replace_signature_parameter(
                proof["bound_interface_signature"], "string")
            proof["bound_interface_member"] = proof["bound_interface_type"] + "." + proof["bound_interface_signature"]

        def wrong_nullable_return(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            proof = target["interface_binding"]
            self.assertIn("Request?>", proof["bound_interface_signature"])
            self.assertIn("Request?>", proof["implementation_signature"])
            proof["bound_interface_signature"] = proof["bound_interface_signature"].replace("Request?>", "Request>")
            proof["bound_interface_member"] = proof["bound_interface_type"] + "." + proof["bound_interface_signature"]
            proof["implementation_signature"] = proof["implementation_signature"].replace("Request?>", "Request>")

        def wrong_tuple_parameter(graph_value, old, new):
            target = candidate_edge(graph_value, search_binding["candidate_identity"], "faceSearch.SearchAsync")
            proof = target["interface_binding"]
            parameter = proof["bound_interface_parameters"][1]
            self.assertIn(old, parameter)
            altered = parameter.replace(old, new)
            parameters = list(proof["bound_interface_parameters"])
            parameters[1] = altered
            proof["bound_interface_parameters"] = parameters
            proof["bound_interface_signature"] = proof["bound_interface_signature"].replace(parameter, altered)
            proof["bound_interface_member"] = proof["bound_interface_type"] + "." + proof["bound_interface_signature"]
            implementation_parameter = proof["implementation_parameters"][1]
            self.assertIn(old, implementation_parameter)
            altered_implementation = implementation_parameter.replace(old, new)
            implementation_parameters = list(proof["implementation_parameters"])
            implementation_parameters[1] = altered_implementation
            proof["implementation_parameters"] = implementation_parameters
            proof["implementation_signature"] = proof["implementation_signature"].replace(
                implementation_parameter, altered_implementation)

        def wrong_tuple_element_type(graph_value):
            wrong_tuple_parameter(graph_value, "long ImageId", "int ImageId")

        def wrong_tuple_element_name(graph_value):
            wrong_tuple_parameter(graph_value, "ImageId", "AssetId")

        def wrong_namespace_parameter(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            proof = target["interface_binding"]
            altered = "None:global::Elsewhere.Request"
            proof["bound_interface_parameters"] = [altered]
            proof["bound_interface_signature"] = replace_signature_parameter(
                proof["bound_interface_signature"], altered)
            proof["bound_interface_member"] = proof["bound_interface_type"] + "." + proof["bound_interface_signature"]
            proof["implementation_parameters"] = [altered]
            proof["implementation_signature"] = replace_signature_parameter(
                proof["implementation_signature"], altered)

        def wrong_array_parameter(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            proof = target["interface_binding"]
            altered = "None:global::Fixture.Request[]"
            proof["bound_interface_parameters"] = [altered]
            proof["bound_interface_signature"] = replace_signature_parameter(
                proof["bound_interface_signature"], altered)
            proof["bound_interface_member"] = proof["bound_interface_type"] + "." + proof["bound_interface_signature"]
            proof["implementation_parameters"] = [altered]
            proof["implementation_signature"] = replace_signature_parameter(
                proof["implementation_signature"], altered)

        def wrong_ref_kind_parameter(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            proof = target["interface_binding"]
            altered = "Ref:global::Fixture.Request"
            proof["bound_interface_parameters"] = [altered]
            proof["bound_interface_signature"] = replace_signature_parameter(
                proof["bound_interface_signature"], altered)
            proof["bound_interface_member"] = proof["bound_interface_type"] + "." + proof["bound_interface_signature"]
            proof["implementation_parameters"] = [altered]
            proof["implementation_signature"] = replace_signature_parameter(
                proof["implementation_signature"], altered)

        def wrong_implementation_array_parameter(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            proof = target["interface_binding"]
            altered = "None:global::Fixture.Request[]"
            proof["implementation_parameters"] = [altered]
            proof["implementation_signature"] = replace_signature_parameter(
                proof["implementation_signature"], altered)

        def wrong_membership_type_source(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            step = target["interface_binding"]["candidate_to_interface_path"][0]
            step["from_type_source"] = json.loads(json.dumps(step["to_type_source"]))

        def matching_type_name_outside_base_list(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            step = target["interface_binding"]["candidate_to_interface_path"][0]
            start = compiler_source.index("IWorker interfaceWorker")
            step["type_syntax_source"] = make_anchor(step["type_syntax_source"], start, start + len("IWorker"))

        def sibling_interface_member_with_widened_declaration(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            target_binding = target["interface_binding"]
            declaration_ref = target_binding["bound_interface_declaration_source"]
            interface_start = ATLAS._compiler_span(declaration_ref)[1]
            sibling_member_start = compiler_source.index("RunChild(Request value)")
            sibling_name_start = sibling_member_start
            sibling_member_end = sibling_member_start + len("RunChild(Request value);")
            widened_end = compiler_source.index("}", sibling_member_end) + 1
            target_binding["bound_interface_declaration_source"] = make_anchor(
                declaration_ref, interface_start, widened_end)
            target_binding["bound_interface_member_source"] = make_anchor(
                target_binding["bound_interface_member_source"], sibling_member_start, sibling_member_end)
            target_binding["bound_interface_member_name_source"] = make_anchor(
                target_binding["bound_interface_member_name_source"], sibling_name_start,
                sibling_name_start + len("RunChild"))

        def widened_membership_owner_contains_sibling_base_list(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            step = target["interface_binding"]["candidate_to_interface_path"][0]
            from_span = ATLAS._compiler_span(step["from_type_source"])
            concrete_start = compiler_source.rfind("public class ConcreteWorker", 0, from_span[1])
            inherited_start = compiler_source.index("public sealed class InheritedWorker")
            concrete_end = compiler_source.rfind("}", 0, inherited_start) + 1
            sibling_start = compiler_source.index("public class VirtualWorker")
            step["from_type_declaration_source"] = make_anchor(
                step["from_type_declaration_source"], sibling_start, concrete_end)

        def attach_valid_proof_to_unrelated_endpoint(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            unrelated = next(node for node in graph_value["nodes"]
                             if node["id"] != target["callee_node_id"])
            target.update({"callee_node_id": unrelated["id"], "callee_method": unrelated["method"],
                           "callee_containing_type": unrelated["containing_type"],
                           "callee_source": unrelated["source"],
                           "callee_lexical_method_fact_id": unrelated["lexical_method_fact_id"]})

        def wrong_fqn_with_recomputed_identity(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            target_binding = target["interface_binding"]
            span = ATLAS._compiler_span(target_binding["candidate_type_source"])
            target_binding["candidate_type"] = "global::Wrong.ConcreteWorker"
            target_binding["candidate_identity"] = "|".join(
                [target_binding["candidate_type"], span[0], str(span[1]), str(span[2])])

        def runtime_flag_true(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            target["runtime_DI_selection_proven"] = True

        def duplicate_supported_candidate(graph_value):
            target = candidate_edge(graph_value, binding["candidate_identity"])
            duplicate = candidate_edge(graph_value, inherited["interface_binding"]["candidate_identity"])
            duplicate["interface_binding"] = json.loads(json.dumps(target["interface_binding"]))

        def sync_compatibility_views(tampered):
            old_graph = original_payload["source_call_graph"]
            new_graph = tampered["source_call_graph"]
            for before, after in zip(old_graph["edges"], new_graph["edges"]):
                if before.get("dispatch_kind") != "interface_implementation_source":
                    continue
                before_span = ATLAS._compiler_span(before["call_site_source"])
                before_identity = before["interface_binding"]["candidate_identity"]
                for projection in tampered["source_call_edges"]:
                    if (projection.get("dispatch_kind") == "interface_implementation_source"
                            and projection.get("caller_lexical_method_fact_id") == before.get("caller_lexical_method_fact_id")
                            and projection.get("callee_lexical_method_fact_id") == before.get("callee_lexical_method_fact_id")
                            and ATLAS._compiler_span(projection.get("call_site_source")) == before_span
                            and projection.get("interface_binding", {}).get("candidate_identity") == before_identity):
                        for key in ("callee_method", "callee_containing_type", "callee_source",
                                    "callee_lexical_method_fact_id", "interface_binding",
                                    "compiler_binding_confirmed", "runtime_reachability_proven",
                                    "runtime_DI_selection_proven"):
                            projection[key] = after[key]
            for before, after in zip(old_graph["unsupported"], new_graph["unsupported"]):
                if before.get("kind") != "unsupported_interface_candidate":
                    continue
                before_span = ATLAS._compiler_span(before["call_site_source"])
                before_identity = before["interface_binding"]["candidate_identity"]
                for projection in tampered["source_call_unresolved"]:
                    if (projection.get("kind") == "unsupported_interface_candidate"
                            and projection.get("caller_method") == before.get("caller_method")
                            and ATLAS._compiler_span(projection.get("source")) == before_span
                            and projection.get("interface_binding", {}).get("candidate_identity") == before_identity):
                        projection["interface_binding"] = after["interface_binding"]
                        projection["reason"] = after["reason"]

        interface_mutations = [
            ("supported and excluded candidate", conflict_with_supported_candidate,
             "compiler interface candidate is both supported and excluded at one callsite"),
            ("wrong overload parameter signature", wrong_overload_signature,
             "compiler interface member source overload disagrees with the compiler-bound parameter signature"),
            ("signature string disagrees with its parameter evidence", wrong_signature_parameters_disagree,
             "compiler interface bound signature disagrees with its parameter evidence"),
            ("nullable task result is forged as nonnullable", wrong_nullable_return,
             "compiler interface member source return type disagrees with its compiler-bound signature"),
            ("tuple element type is forged", wrong_tuple_element_type,
             "compiler interface member source overload disagrees with the compiler-bound parameter signature"),
            ("tuple element name is forged", wrong_tuple_element_name,
             "compiler interface member source overload disagrees with the compiler-bound parameter signature"),
            ("qualified parameter is not collapsed", wrong_namespace_parameter,
             "compiler interface member source overload disagrees with the compiler-bound parameter signature"),
            ("array parameter is not collapsed", wrong_array_parameter,
             "compiler interface member source overload disagrees with the compiler-bound parameter signature"),
            ("ref kind is not collapsed", wrong_ref_kind_parameter,
             "compiler interface member source overload disagrees with the compiler-bound parameter signature"),
            ("implementation array parameter is not collapsed", wrong_implementation_array_parameter,
             "compiler interface implementation source disagrees with the bound interface signature"),
            ("wrong membership source type", wrong_membership_type_source,
             "compiler interface membership source type anchor does not identify one exact saved lexical type fact"),
            ("matching type name outside base list", matching_type_name_outside_base_list,
             "compiler interface membership syntax anchor is invalid"),
            ("sibling interface member under widened declaration", sibling_interface_member_with_widened_declaration,
             "compiler source-call lexical owner is not the innermost enclosing type"),
            ("widened membership owner contains sibling genuine base list",
             widened_membership_owner_contains_sibling_base_list,
             "compiler interface membership declaration is not one exact lexical type owner"),
            ("valid interface proof on unrelated callee", attach_valid_proof_to_unrelated_endpoint,
             "compiler interface implementation evidence disagrees with its edge endpoint"),
            ("wrong FQN with candidate identity resealed", wrong_fqn_with_recomputed_identity,
             "compiler interface candidate display identity disagrees with its lexical owner"),
            ("runtime selection claim", runtime_flag_true,
             "compiler source-call edge has invalid proof labels"),
            ("duplicate callsite candidate identity", duplicate_supported_candidate,
             "compiler source-call graph contains a duplicate callsite edge"),
        ]
        with sqlite3.connect(self.db) as connection:
            original_row = connection.execute(
                "SELECT payload_json FROM atlas_compiler_supplements WHERE snapshot_id=?",
                (snapshot["snapshot_id"],)).fetchone()
        original_payload = json.loads(original_row[0])
        compiler_route_fact_id = relationships[0]["lexical_route_fact_id"]
        for label, mutate, diagnostic in interface_mutations:
            tampered = json.loads(json.dumps(original_payload))
            mutate(tampered["source_call_graph"])
            sync_compatibility_views(tampered)
            if label == "supported and excluded candidate":
                graph_value = tampered["source_call_graph"]
                positive_keys = {(edge["caller_node_id"], ATLAS._compiler_span(edge["call_site_source"]),
                                  edge["interface_binding"]["candidate_identity"])
                                 for edge in graph_value["edges"]
                                 if isinstance(edge.get("interface_binding"), dict)}
                excluded_keys = {(item["caller_node_id"], ATLAS._compiler_span(item["call_site_source"]),
                                  item["interface_binding"]["candidate_identity"])
                                 for item in graph_value["unsupported"]
                                 if item.get("kind") == "unsupported_interface_candidate"}
                self.assertTrue(positive_keys & excluded_keys, "tamper must create a real supported/excluded candidate conflict")
            encoded = reseal(tampered)
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                                   (tampered["content_sha256"], encoded, snapshot["snapshot_id"]))
            db_before_refusal = self.db.read_bytes()
            impact_refused = self.impact("Support.WorkerHelper", max_tokens=100000, expect=None)
            self.assertEqual(impact_refused.returncode, 2, label + ": impact accepted tampered graph: " + impact_refused.stdout)
            self.assertEqual(impact_refused.stdout, "", label)
            self.assertIn(diagnostic, impact_refused.stderr, label)
            self.assertEqual(self.db.read_bytes(), db_before_refusal, label)
            pack_refused = self.evidence_pack(compiler_route_fact_id, max_tokens=100000, expect=None)
            self.assertEqual(pack_refused.returncode, 2, label + ": evidence-pack accepted tampered graph: " + pack_refused.stdout)
            self.assertEqual(pack_refused.stdout, "", label)
            self.assertIn(diagnostic, pack_refused.stderr, label)
            self.assertEqual(self.db.read_bytes(), db_before_refusal, label)
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_compiler_supplements SET content_sha256=?,payload_json=? WHERE snapshot_id=?",
                                   (original_payload["content_sha256"], original_row[0], snapshot["snapshot_id"]))

        source.write_text(compiler_source +
                          "\npublic static class Alternate { public readonly record struct ResolvedAssociation(long LocationId); }\n",
                          encoding="utf-8")
        git(self.repo, "add", "--", "Fixture.cs")
        snapshot = self.index()
        db_before_ambiguous_type_index = self.db.read_bytes()
        alternate_indexed = self.cli("compiler-index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db),
                                     "--project", "Fixture.csproj", "--framework", "net8.0", expect=2)
        self.assertEqual(alternate_indexed.stdout, "")
        self.assertIn("compiler interface member source overload disagrees with the compiler-bound parameter signature",
                      alternate_indexed.stderr)
        self.assertIn("global::Fixture.ResolvedAssociation", alternate_indexed.stderr)
        self.assertEqual(self.db.read_bytes(), db_before_ambiguous_type_index)

        broken = self.repo / "Broken.cs"
        broken.write_text("namespace Fixture; public class Broken { public void M() { MissingSymbol(); } }", encoding="utf-8")
        git(self.repo, "add", "--", "Broken.cs")
        self.index()
        database_before = self.db.read_bytes()
        fatal = self.cli("compiler-index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db),
                         "--project", "Fixture.csproj", "--framework", "net8.0", expect=2)
        self.assertIn("compiler errors", fatal.stderr)
        self.assertEqual(self.db.read_bytes(), database_before)

    def test_impact_view_refuses_ambiguous_method_and_stale_or_unsafe_source(self):
        source = self.repo / "Calls.cs"
        source.write_text('''namespace First
{
    class Target { static void Work() { } }
}
namespace Second
{
    class Target { static void Work() { } }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Calls.cs")
        self.index()
        db_before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        ambiguous = self.impact("Target.Work", expect=2)
        self.assertEqual(ambiguous.stdout, "")
        self.assertIn("ambiguous", ambiguous.stderr)
        selected = json.loads(self.impact("First.Target.Work").stdout)
        self.assertEqual(selected["candidate_count"], 0)
        unknown = self.impact("First.Target.Missing", expect=2)
        self.assertEqual(unknown.stdout, "")
        self.assertIn("not found", unknown.stderr)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), db_before)

        source.write_text(source.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")
        stale = self.impact("First.Target.Work", expect=2)
        self.assertEqual(stale.stdout, "")
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale.stderr)

        source.unlink()
        source.symlink_to(self.root / "outside.cs")
        unsafe = self.impact("First.Target.Work", expect=2)
        self.assertEqual(unsafe.stdout, "")
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", unsafe.stderr)

    def test_impact_source_reader_does_not_follow_a_tracked_path_symlink(self):
        outside = self.root / "outside.cs"
        outside.write_text("class Secret { static void Work() {} }", encoding="utf-8")
        link = self.repo / "Link.cs"
        link.symlink_to(outside)
        root_fd = os.open(self.repo, os.O_RDONLY | os.O_DIRECTORY)
        try:
            evidence = ATLAS._read_working_file(root_fd, "Link.cs", collect_source=True)
        finally:
            os.close(root_fd)
        self.assertEqual(evidence["type"], "symlink")
        self.assertNotIn("_source_bytes", evidence)

    def refresh_fixture(self, claim_count=8):
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 1; } }\n", encoding="utf-8")
        (self.repo / "Flow.cs").write_text('''namespace Demo;
[Route("api/customer")]
class CustomerController(IHandler handler)
{
    [HttpPost("save")]
    void Save() { handler.Handle(); }
}
''', encoding="utf-8")
        (self.repo / "Handler.cs").write_text('''namespace Demo;
class Handler(IStore store)
{
    void Handle() { store.SaveAsync(); store.GetAsync(); }
}
class Store { void SaveAsync() {} void GetAsync() {} }
class Registrations { void Add() { services.AddScoped<IHandler, Handler>(); services.AddScoped<IStore, Store>(); } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "Other.cs", "Flow.cs", "Handler.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f["kind"] == "route_action")
        flow = {
            "overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"], "title": "Refresh carry fixture",
            "reviewed_conclusions": [
                {"claim": f"Reviewed route claim {index}.",
                 "evidence": [{"fact_id": route["id"], "source": route["source"]}]}
                for index in range(claim_count)
            ],
        }
        flow_path = self.root / "refresh.flow.json"
        flow_path.write_text(json.dumps(flow), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                                       "--input", os.fspath(flow_path)).stdout)
        receipt = {"receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"],
                   "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"],
                   "extractor_identity": graph["extractor_identity"], "reviewer_identity": "fixture reviewer",
                   "reviewer_model": "GPT-6.1 Sol High", "decision": "accepted",
                   "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "Each route claim cites the saved route source fact."}
        receipt_path = self.root / "refresh.review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        reviewed = json.loads(self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                                       "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_path)).stdout)
        binding_path, _, _ = self.route_binding_document(saved, graph, route, attached, reviewed, "refresh-binding")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                 "--input", os.fspath(binding_path))
        return saved, graph, route, attached, reviewed

    def route_refresh(self, saved, route, expect=0, max_tokens=100000):
        return self.cli("route-refresh", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                        "--from-snapshot", saved["snapshot_id"], "--route-fact-id", route["id"],
                        "--max-tokens", str(max_tokens), expect=expect)

    def coverage_fixture(self, count=6):
        methods = "\n".join(f'    [HttpGet("item-{index}")] void Item{index}() {{}}' for index in range(count))
        source = self.repo / "Routes.cs"
        source.write_text(f'''[Route("api/test")]
class TestController
{{
{methods}
}}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        return saved, graph, sorted((fact for fact in graph["facts"] if fact["kind"] == "route_action"), key=lambda fact: fact["id"])

    def evidence_fixture(self, extra_registration="", shadow=False):
        handler_body = "store.SaveAsync(); store.GetAsync();"
        if shadow:
            handler_body = "var store = new Store(); store.SaveAsync(); store.GetAsync();"
        source = self.repo / "Flow.cs"
        source.write_text(f'''namespace Demo;
[Route("api/customer")]
class CustomerController(IHandler handler)
{{
    [HttpPost("save")]
    void Save() {{ handler.Handle(); }}
}}
class Handler(IStore store)
{{
    void Handle() {{ {handler_body} }}
}}
class Store {{ void SaveAsync() {{}} void GetAsync() {{}} }}
class Registrations {{ void Add() {{ services.AddScoped<IHandler, Handler>(); services.AddScoped<IStore, Store>(); {extra_registration} }} }}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Flow.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f["kind"] == "route_action")
        return saved, graph, route

    def route_map_fixture(self, title="Route map test"):
        saved, graph, route = self.evidence_fixture()
        draft = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": title,
            "reviewed_conclusions": [{
                "claim": "The selected route invokes its saved action method.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        draft_path = self.root / "luna-draft.json"
        draft_path.write_bytes(json.dumps(draft, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
        prepared = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(draft_path), "--max-tokens", "500000",
        )
        packet = json.loads(prepared.stdout)
        packet_path = self.root / "route-map-review-packet.json"
        packet_path.write_bytes(prepared.stdout.encode("ascii"))
        review = {
            "review_schema_version": 1,
            "packet_sha256": packet["packet_sha256"],
            "evidence_sha256": packet["evidence_sha256"],
            "draft_sha256": packet["draft_sha256"],
            # This is an explicitly synthetic mechanics fixture in a disposable DB,
            # not a semantic review or a claim that Sol reviewed this test content.
            "reviewer_identity": "synthetic CLI mechanics fixture",
            "reviewer_model": "GPT-6.1 Sol High",
            "reviewed_at": "2026-10-06T12:00:00Z",
            "decision": "accepted",
            "assignment_review": {
                "decision": "accepted",
                "basis": "The assignment is limited to this route and this complete evidence packet.",
            },
            "conclusion_reviews": [{
                "conclusion_number": 1,
                "decision": "accepted",
                "basis": "The claim matches the cited route action declaration in the supplied packet.",
            }],
            "route_association_review": {
                "decision": "accepted",
                "basis": "This map describes the exact selected route action shown by its cited fact.",
            },
        }
        review_path = self.root / "route-map-independent-review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        return saved, graph, route, draft_path, packet_path, packet, review_path, review

    def route_map_cli(self, command, packet_path, review_path, expect=0):
        return self.cli(command, "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                        "--packet-file", os.fspath(packet_path), "--review-file", os.fspath(review_path), expect=expect)

    def test_route_map_cli_publish_is_atomic_idempotent_and_reusable(self):
        saved, _graph, route, _draft, packet_path, packet, review_path, _review = self.route_map_fixture()
        before_review = self.db.read_bytes()
        reviewed = json.loads(self.route_map_cli("route-map-review", packet_path, review_path).stdout)
        self.assertEqual(reviewed["result"], "accepted")
        self.assertEqual(reviewed["writes"], 0)
        self.assertEqual(self.db.read_bytes(), before_review)

        published = json.loads(self.route_map_cli("route-map-publish", packet_path, review_path).stdout)
        self.assertEqual(published["result"], "published")
        self.assertFalse(published["idempotent"])
        with sqlite3.connect(self.db) as connection:
            receipt_json = connection.execute(
                "SELECT receipt_json FROM atlas_flow_reviews WHERE snapshot_id=? AND overlay_id=?",
                (saved["snapshot_id"], published["overlay_id"]),
            ).fetchone()[0]
        self.assertNotIn("route_map_review_sha256", json.loads(receipt_json))
        self.assertNotIn("revision", json.loads(receipt_json))
        repeated = json.loads(self.route_map_cli("route-map-publish", packet_path, review_path).stdout)
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(repeated["overlay_id"], published["overlay_id"])

        found = json.loads(self.cli(
            "route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--max-tokens", "100000",
        ).stdout)
        self.assertEqual(found["result"], "fresh")
        self.assertEqual(found["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(found["association"]["binding"]["overlay_id"], published["overlay_id"])
        self.assertEqual(found["claim_selection"]["omitted_claims"], 0)

        focused = json.loads(self.cli(
            "focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--snapshot", saved["snapshot_id"], "--overlay", published["overlay_id"], "--max-tokens", "100000",
        ).stdout)
        self.assertEqual(focused["result"], "fresh")
        self.assertEqual(focused["review_status"], "accepted")

        question = self.root / "question.txt"
        answer = self.root / "answer.txt"
        question.write_text("Which method handles this route?\n", encoding="utf-8")
        answer.write_text("The route invokes Save.\n", encoding="utf-8")
        checked = json.loads(self.cli(
            "answer-check", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--snapshot", saved["snapshot_id"], "--overlay", published["overlay_id"],
            "--question-file", os.fspath(question), "--draft-file", os.fspath(answer),
        ).stdout)
        self.assertEqual(checked["result"], "semantic_review_required")
        self.assertEqual(checked["binding"]["overlay_id"], published["overlay_id"])
        self.assertEqual(packet["evidence_sha256"], published["evidence_sha256"])

        conflict = dict(_review)
        conflict["route_association_review"] = dict(
            conflict["route_association_review"],
            basis="A conflicting review cannot replace the immutable route association.",
        )
        conflict_path = self.root / "conflicting-review.json"
        conflict_path.write_text(json.dumps(conflict), encoding="utf-8")
        conflict_result = self.route_map_cli("route-map-publish", packet_path, conflict_path, expect=2)
        self.assertIn("review receipt is immutable", conflict_result.stderr)

    def test_route_map_rejection_and_undersized_packet_do_not_write(self):
        _saved, _graph, route = self.evidence_fixture()
        draft = {
            "overlay_schema_version": 1,
            "snapshot_id": self.index()["snapshot_id"],
        }
        graph = self.graph(draft["snapshot_id"])
        draft.update({
            "extractor_identity": graph["extractor_identity"], "title": "Rejected map",
            "reviewed_conclusions": [{"claim": "This route invokes its saved action.",
                                      "evidence": [{"fact_id": route["id"], "source": route["source"]}]}],
        })
        draft_path = self.root / "rejected-draft.json"
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        evidence_bytes = len(self.evidence_pack(route["id"], 500000).stdout.encode("ascii"))
        before = self.db.read_bytes()
        too_small = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(draft_path),
            "--max-tokens", str(evidence_bytes + 5), expect=2,
        )
        self.assertEqual(too_small.stdout, "")
        self.assertIn("complete route-map review packet requires", too_small.stderr)
        self.assertEqual(self.db.read_bytes(), before)

        prepared = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(draft_path), "--max-tokens", "500000",
        )
        packet = json.loads(prepared.stdout)
        packet_path = self.root / "rejected-packet.json"
        packet_path.write_text(prepared.stdout, encoding="ascii")
        review = {
            "review_schema_version": 1, "packet_sha256": packet["packet_sha256"],
            "evidence_sha256": packet["evidence_sha256"], "draft_sha256": packet["draft_sha256"],
            "reviewer_identity": "synthetic rejection mechanics fixture", "reviewer_model": "GPT-6.1 Sol High",
            "reviewed_at": "2026-10-06T12:00:00Z", "decision": "rejected",
            "assignment_review": {"decision": "rejected", "basis": "The assignment packet is rejected by this mechanics fixture."},
            "conclusion_reviews": [{"conclusion_number": 1, "decision": "rejected",
                                    "basis": "The claim is rejected by this mechanics fixture for a negative path."}],
            "route_association_review": {"decision": "rejected", "basis": "The route association is rejected by this mechanics fixture."},
        }
        review_path = self.root / "rejected-review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        result = json.loads(self.route_map_cli("route-map-review", packet_path, review_path).stdout)
        self.assertEqual(result["result"], "rejected")
        self.assertEqual(self.db.read_bytes(), before)
        rejected = self.route_map_cli("route-map-publish", packet_path, review_path, expect=2)
        self.assertIn("review was rejected; no atlas records were written", rejected.stderr)
        self.assertEqual(self.db.read_bytes(), before)

    def test_route_map_publish_rolls_back_all_records_when_binding_insert_fails(self):
        _saved, _graph, _route, _draft, packet_path, _packet, review_path, _review = self.route_map_fixture()
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "CREATE TABLE atlas_route_bindings (snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, "
                "overlay_id TEXT NOT NULL, binding_hash TEXT NOT NULL, association_review_hash TEXT NOT NULL, "
                "payload_json TEXT NOT NULL, PRIMARY KEY(snapshot_id, route_fact_id, overlay_id))"
            )
            connection.execute(
                "CREATE TRIGGER reject_route_binding BEFORE INSERT ON atlas_route_bindings "
                "BEGIN SELECT RAISE(ABORT, 'forced binding insert failure'); END"
            )
        result = self.route_map_cli("route-map-publish", packet_path, review_path, expect=2)
        self.assertIn("forced binding insert failure", result.stderr)
        with sqlite3.connect(self.db) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("atlas_reviewed_flows", tables)
            self.assertNotIn("atlas_flow_reviews", tables)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM atlas_route_bindings").fetchone()[0], 0)

    def test_route_map_rejects_reserved_content_hash_without_writes(self):
        _saved, _graph, route, draft_path, packet_path, packet, review_path, review = self.route_map_fixture()
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()

        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        draft["content_hash"] = "caller-computed-value"
        draft_path.write_text(json.dumps(draft, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
        prepare = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(draft_path),
            "--max-tokens", "500000", expect=2,
        )
        self.assertIn("must not supply content_hash", prepare.stderr)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

        # Forge every caller-controlled digest so publish reaches packet validation.
        forged = dict(packet)
        forged_draft = json.loads(packet["draft"])
        forged_draft["content_hash"] = "caller-computed-value"
        forged["draft"] = json.dumps(forged_draft, ensure_ascii=True, separators=(",", ":"))
        forged["draft_sha256"] = hashlib.sha256(forged["draft"].encode("utf-8")).hexdigest()
        unsigned = {key: value for key, value in forged.items() if key != "packet_sha256"}
        forged["packet_sha256"] = hashlib.sha256(json.dumps(
            unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii") + b"\n").hexdigest()
        packet_path.write_text(
            json.dumps(forged, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="ascii",
        )
        forged_review = dict(review, packet_sha256=forged["packet_sha256"],
                             draft_sha256=forged["draft_sha256"])
        review_path.write_text(json.dumps(forged_review), encoding="utf-8")
        publish = self.route_map_cli("route-map-publish", packet_path, review_path, expect=2)
        self.assertIn("must not supply content_hash", publish.stderr)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_route_map_review_rejects_stale_or_tampered_packet_and_mapped_route(self):
        _saved, _graph, route, draft_path, packet_path, packet, review_path, _review = self.route_map_fixture()
        packet_doc = json.loads(packet_path.read_text(encoding="ascii"))
        packet_doc["draft"] = packet_doc["draft"].replace("selected route", "different route")
        packet_path.write_text(json.dumps(packet_doc), encoding="ascii")
        tampered = self.route_map_cli("route-map-review", packet_path, review_path, expect=2)
        self.assertIn("route-map packet hash is invalid", tampered.stderr)

        included = {item["fact_id"] for field in ("source_snippets", "candidate_snippets")
                    for item in packet["complete_evidence_packet"][field]}
        omitted = next(fact for fact in _graph["facts"]
                       if fact.get("source") and fact["id"] not in included)
        unsupported_draft = json.loads(packet["draft"])
        unsupported_draft["reviewed_conclusions"][0]["evidence"].append(
            {"fact_id": omitted["id"], "source": omitted["source"]},
        )
        forged = dict(packet)
        forged["draft"] = json.dumps(unsupported_draft, ensure_ascii=True, separators=(",", ":"))
        forged["draft_sha256"] = hashlib.sha256(forged["draft"].encode("utf-8")).hexdigest()
        forged["claims"] = [{"conclusion_number": 1,
                              "claim": unsupported_draft["reviewed_conclusions"][0]["claim"],
                              "evidence": unsupported_draft["reviewed_conclusions"][0]["evidence"]}]
        unsigned = {key: value for key, value in forged.items() if key != "packet_sha256"}
        forged["packet_sha256"] = hashlib.sha256(json.dumps(
            unsigned, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii") + b"\n").hexdigest()
        packet_path.write_text(json.dumps(forged, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
        excluded_citation = self.route_map_cli("route-map-review", packet_path, review_path, expect=2)
        self.assertIn("citation fact is not included with its exact source", excluded_citation.stderr)

        packet_path.write_text(json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
        changed = self.repo / "Flow.cs"
        changed.write_text(changed.read_text(encoding="utf-8") + "// changed after review packet\n", encoding="utf-8")
        stale = self.route_map_cli("route-map-review", packet_path, review_path, expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale.stderr)
        git(self.repo, "add", "--", "Flow.cs")
        self.index()
        stale_again = self.route_map_cli("route-map-publish", packet_path, review_path, expect=2)
        self.assertIn("route-map packet is stale", stale_again.stderr)

        # A separate fresh route with one existing accepted link cannot enter this one-open-route path.
        self.repo = self.repo
        saved, graph, route = self.evidence_fixture()
        attached, receipt = self.reviewed_route_map(saved, graph, route, "Pre-mapped route")
        binding_path, _binding, _association = self.route_binding_document(saved, graph, route, attached, receipt)
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                 "--input", os.fspath(binding_path))
        draft = {"overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"],
                 "extractor_identity": graph["extractor_identity"], "title": "Second map",
                 "reviewed_conclusions": [{"claim": "This is another route map.",
                                           "evidence": [{"fact_id": route["id"], "source": route["source"]}]}]}
        second_draft = self.root / "second-map.json"
        second_draft.write_text(json.dumps(draft), encoding="utf-8")
        refused = self.cli("route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--draft-file", os.fspath(second_draft),
                           "--max-tokens", "500000", expect=2)
        self.assertIn("requires one open route with zero accepted associations", refused.stderr)

    def test_route_map_revision_preserves_predecessor_and_publishes_one_current_successor(self):
        saved, graph, route, _draft, _packet_path, _packet, _review_path, _review = self.route_map_fixture("Original route map")
        first = json.loads(self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(_draft), "--max-tokens", "500000",
        ).stdout)
        # The fixture helper returned a prepared packet; publish that exact map first.
        first_packet_path = self.root / "first-route-map-packet.json"
        first_review_path = self.root / "first-route-map-review.json"
        first_packet_path.write_text(json.dumps(first), encoding="utf-8")
        first_review = dict(_review, packet_sha256=first["packet_sha256"], evidence_sha256=first["evidence_sha256"],
                            draft_sha256=first["draft_sha256"])
        first_review_path.write_text(json.dumps(first_review), encoding="utf-8")
        first_published = json.loads(self.route_map_cli("route-map-publish", first_packet_path, first_review_path).stdout)

        successor_draft = {
            "overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"], "title": "Corrected route map",
            "reviewed_conclusions": [{
                "claim": "The corrected map keeps the selected action identity in view.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        successor_draft_path = self.root / "successor-route-map.json"
        successor_draft_path.write_text(json.dumps(successor_draft), encoding="utf-8")
        prepared = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(successor_draft_path),
            "--max-tokens", "500000", "--revise",
        )
        packet = json.loads(prepared.stdout)
        self.assertEqual(packet["revision"]["predecessor"]["overlay_id"], first_published["overlay_id"])
        self.assertEqual(packet["revision"]["predecessor"]["review_receipt"]["receipt_hash"], first_published["receipt_hash"])
        self.assertEqual(packet["revision"]["predecessor"]["binding"]["route_fact_id"], route["id"])
        successor_packet_path = self.root / "successor-route-map-packet.json"
        successor_packet_path.write_bytes(prepared.stdout.encode("ascii"))
        review = {
            "review_schema_version": 1, "packet_sha256": packet["packet_sha256"],
            "evidence_sha256": packet["evidence_sha256"], "draft_sha256": packet["draft_sha256"],
            "reviewer_identity": "independent revision reviewer", "reviewer_model": "GPT-6.1 Sol High",
            "reviewed_at": "2026-10-07T12:00:00Z", "decision": "accepted",
            "assignment_review": {"decision": "accepted", "basis": "The revised assignment remains bounded to the selected route and current evidence."},
            "conclusion_reviews": [{"conclusion_number": 1, "decision": "accepted",
                                    "basis": "The revised wording is supported by the exact route source span provided."}],
            "route_association_review": {"decision": "accepted",
                                         "basis": "The successor continues to identify the exact selected route action."},
        }
        review_path = self.root / "successor-route-map-review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        stale_draft = dict(successor_draft, title="Different successor from stale predecessor")
        stale_path = self.root / "stale-successor.json"
        stale_path.write_text(json.dumps(stale_draft), encoding="utf-8")
        stale_prepared = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(stale_path),
            "--max-tokens", "500000", "--revise",
        )
        stale_packet = json.loads(stale_prepared.stdout)
        stale_packet_path = self.root / "stale-successor-packet.json"
        stale_packet_path.write_bytes(stale_prepared.stdout.encode("ascii"))
        stale_review = dict(review, packet_sha256=stale_packet["packet_sha256"],
                            evidence_sha256=stale_packet["evidence_sha256"],
                            draft_sha256=stale_packet["draft_sha256"])
        stale_review_path = self.root / "stale-successor-review.json"
        stale_review_path.write_text(json.dumps(stale_review), encoding="utf-8")
        published = json.loads(self.route_map_cli("route-map-publish", successor_packet_path, review_path).stdout)
        self.assertNotEqual(published["overlay_id"], first_published["overlay_id"])
        self.assertFalse(published["idempotent"])
        repeated = json.loads(self.route_map_cli("route-map-publish", successor_packet_path, review_path).stdout)
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(repeated["overlay_id"], published["overlay_id"])

        found = json.loads(self.route_find(route["id"], max_tokens=30000).stdout)
        self.assertEqual(found["result"], "fresh")
        self.assertEqual(found["association_count"], 1)
        self.assertEqual(found["association"]["binding"]["overlay_id"], published["overlay_id"])
        self.assertEqual(found["association"]["binding"]["flow_review_receipt_hash"], published["receipt_hash"])
        old_flow = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                                      "--overlay", first_published["overlay_id"]).stdout)
        self.assertEqual(old_flow["review_status"], "accepted")
        self.assertEqual(old_flow["review_receipt"]["receipt_hash"], first_published["receipt_hash"])
        with sqlite3.connect(self.db) as connection:
            edge_count = connection.execute("SELECT COUNT(*) FROM atlas_route_supersessions").fetchone()[0]
            map_count = connection.execute("SELECT COUNT(*) FROM atlas_reviewed_flows WHERE snapshot_id=?",
                                            (saved["snapshot_id"],)).fetchone()[0]
        self.assertEqual(edge_count, 1)
        self.assertEqual(map_count, 2)
        successor_flow = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
                                             "--overlay", published["overlay_id"]).stdout)
        self.assertEqual(successor_flow["review_receipt"]["revision"]["predecessor_overlay_id"], first_published["overlay_id"])
        self.assertEqual(successor_flow["review_receipt"]["revision"]["predecessor_binding_hash"],
                         packet["revision"]["predecessor"]["binding_hash"])
        coverage = json.loads(self.coverage().stdout)
        self.assertEqual(coverage["counts"]["one_reviewed_link"], 1)

        stale = self.route_map_cli("route-map-publish", stale_packet_path, stale_review_path, expect=2)
        self.assertIn("route-map revision is stale", stale.stderr)

        third_draft = dict(successor_draft, title="Third map in revision chain")
        third_draft_path = self.root / "third-route-map.json"
        third_draft_path.write_text(json.dumps(third_draft), encoding="utf-8")
        third_prepared = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(third_draft_path),
            "--max-tokens", "500000", "--revise",
        )
        third_packet = json.loads(third_prepared.stdout)
        third_packet_path = self.root / "third-route-map-packet.json"
        third_packet_path.write_bytes(third_prepared.stdout.encode("ascii"))
        third_review = dict(review, packet_sha256=third_packet["packet_sha256"],
                            evidence_sha256=third_packet["evidence_sha256"],
                            draft_sha256=third_packet["draft_sha256"],
                            reviewer_identity="independent third revision reviewer")
        third_review_path = self.root / "third-route-map-review.json"
        third_review_path.write_text(json.dumps(third_review), encoding="utf-8")
        third = json.loads(self.route_map_cli("route-map-publish", third_packet_path, third_review_path).stdout)
        self.assertFalse(third["idempotent"])

        historical_retry = json.loads(self.route_map_cli("route-map-publish", successor_packet_path, review_path).stdout)
        self.assertTrue(historical_retry["idempotent"])
        self.assertEqual(historical_retry["overlay_id"], published["overlay_id"])
        stale_after_chain = self.route_map_cli("route-map-publish", stale_packet_path, stale_review_path, expect=2)
        self.assertIn("route-map revision is stale", stale_after_chain.stderr)
        changed_old_review = dict(review, reviewer_identity="different reviewer for old edge")
        changed_old_review_path = self.root / "changed-old-successor-review.json"
        changed_old_review_path.write_text(json.dumps(changed_old_review), encoding="utf-8")
        changed_review_retry = self.route_map_cli(
            "route-map-publish", successor_packet_path, changed_old_review_path, expect=2,
        )
        self.assertIn("route-map revision is stale", changed_review_retry.stderr)
        current_after_retries = json.loads(self.route_find(route["id"], max_tokens=30000).stdout)
        self.assertEqual(current_after_retries["association"]["binding"]["overlay_id"], third["overlay_id"])

        (self.repo / "Unrelated.txt").write_text("unrelated snapshot change\n", encoding="utf-8")
        git(self.repo, "add", "--", "Unrelated.txt")
        refreshed = json.loads(self.cli(
            "route-refresh", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--from-snapshot", saved["snapshot_id"], "--route-fact-id", route["id"], "--max-tokens", "500000",
        ).stdout)
        carried = json.loads(self.route_find(route["id"], max_tokens=30000).stdout)
        self.assertEqual(carried["snapshot_id"], refreshed["snapshot_id"])
        self.assertEqual(carried["result"], "fresh")
        self.assertEqual(carried["association"]["carry_provenance"]["origin_overlay_id"], third["overlay_id"])
        carry_revision_draft = {
            "overlay_schema_version": 1, "snapshot_id": refreshed["snapshot_id"],
            "extractor_identity": graph["extractor_identity"], "title": "Forbidden carried revision",
            "reviewed_conclusions": [{"claim": "The route remains selected.",
                                      "evidence": [{"fact_id": route["id"], "source": route["source"]}]}],
        }
        carry_revision_path = self.root / "carried-revision.json"
        carry_revision_path.write_text(json.dumps(carry_revision_draft), encoding="utf-8")
        carry_refused = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(carry_revision_path),
            "--max-tokens", "500000", "--revise", expect=2,
        )
        self.assertIn("carried maps cannot be revised", carry_refused.stderr)
        with sqlite3.connect(self.db) as connection:
            row_id, payload_json = connection.execute(
                "SELECT rowid,payload_json FROM atlas_route_supersessions ORDER BY predecessor_overlay_id LIMIT 1"
            ).fetchone()
            tampered_edge = json.loads(payload_json)
            tampered_edge["packet_sha256"] = "0" * 64
            connection.execute("UPDATE atlas_route_supersessions SET payload_json=? WHERE rowid=?",
                               (json.dumps(tampered_edge), row_id))
        tampered_lookup = self.route_find(route["id"], max_tokens=30000, expect=2)
        self.assertIn("supersession integrity hash is invalid", tampered_lookup.stderr)
        self.assertIn("supersession integrity hash is invalid", self.coverage(expect=2).stderr)

    def test_route_map_revision_rolls_back_successor_records_when_edge_write_fails(self):
        saved, graph, route, draft_path, packet_path, packet, review_path, review = self.route_map_fixture("Original before rollback")
        first = json.loads(self.route_map_cli("route-map-publish", packet_path, review_path).stdout)
        successor_draft = {
            "overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"], "title": "Must roll back",
            "reviewed_conclusions": [{
                "claim": "The route identity is retained in this attempted revision.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        successor_draft_path = self.root / "rollback-successor.json"
        successor_draft_path.write_text(json.dumps(successor_draft), encoding="utf-8")
        prepared = self.cli(
            "route-map-prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--route-fact-id", route["id"], "--draft-file", os.fspath(successor_draft_path),
            "--max-tokens", "500000", "--revise",
        )
        successor_packet = json.loads(prepared.stdout)
        successor_packet_path = self.root / "rollback-successor-packet.json"
        successor_packet_path.write_bytes(prepared.stdout.encode("ascii"))
        successor_review = dict(review, packet_sha256=successor_packet["packet_sha256"],
                                evidence_sha256=successor_packet["evidence_sha256"],
                                draft_sha256=successor_packet["draft_sha256"])
        successor_review_path = self.root / "rollback-successor-review.json"
        successor_review_path.write_text(json.dumps(successor_review), encoding="utf-8")
        with sqlite3.connect(self.db) as connection:
            before = tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                           for table in ("atlas_reviewed_flows", "atlas_flow_reviews", "atlas_route_bindings"))
            connection.execute(
                "CREATE TABLE atlas_route_supersessions ("
                "snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, predecessor_overlay_id TEXT NOT NULL, "
                "successor_overlay_id TEXT NOT NULL, edge_hash TEXT NOT NULL, payload_json TEXT NOT NULL, "
                "PRIMARY KEY(snapshot_id, route_fact_id, predecessor_overlay_id), "
                "UNIQUE(snapshot_id, route_fact_id, successor_overlay_id))"
            )
            connection.execute(
                "CREATE TRIGGER force_supersession_insert_failure BEFORE INSERT ON atlas_route_supersessions "
                "BEGIN SELECT RAISE(ABORT, 'forced supersession write failure'); END"
            )
        refused = self.route_map_cli("route-map-publish", successor_packet_path, successor_review_path, expect=2)
        self.assertIn("forced supersession write failure", refused.stderr)
        with sqlite3.connect(self.db) as connection:
            after = tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                          for table in ("atlas_reviewed_flows", "atlas_flow_reviews", "atlas_route_bindings"))
            edges = connection.execute("SELECT COUNT(*) FROM atlas_route_supersessions").fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(edges, 0)
        current = json.loads(self.route_find(route["id"], max_tokens=30000).stdout)
        self.assertEqual(current["association"]["binding"]["overlay_id"], first["overlay_id"])

    def reviewed_route_map(self, saved, graph, route, title="Reviewed route map"):
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": title,
            "reviewed_conclusions": [{
                "claim": "The reviewed map describes the route action.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        overlay_path = self.root / f"{title.replace(' ', '-')}.flow.json"
        overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli(
            "flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
            "--input", os.fspath(overlay_path),
        ).stdout)
        receipt = {
            "receipt_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "overlay_id": attached["overlay_id"],
            "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"],
            "reviewer_identity": "independent fixture review",
            "reviewer_model": "GPT-6.1 Sol High",
            "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z",
            "review_basis": "The route action citation and reviewed map wording were checked for this fixture.",
        }
        receipt_path = self.root / f"{title.replace(' ', '-')}.review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        saved_receipt = json.loads(self.cli(
            "flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"],
            "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_path),
        ).stdout)
        return attached, saved_receipt

    def route_binding_document(self, saved, graph, route, attached, flow_receipt, title="route-binding"):
        binding = {
            "binding_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "route_fact_id": route["id"],
            "overlay_id": attached["overlay_id"],
            "flow_review_receipt_hash": flow_receipt["receipt_hash"],
        }
        binding_hash = hashlib.sha256(json.dumps(
            binding, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("ascii")).hexdigest()
        association_review = {
            "review_schema_version": 1,
            "binding_hash": binding_hash,
            **binding,
            "reviewer_identity": "independent route association reviewer",
            "reviewer_model": "GPT-6.1 Sol High",
            "decision": "accepted",
            "reviewed_at": "2026-10-06T12:30:00Z",
            "review_basis": "The route identity and selected flow purpose were checked against the cited evidence.",
        }
        path = self.root / f"{title}.binding.json"
        path.write_text(json.dumps({"binding": binding, "association_review": association_review}), encoding="utf-8")
        return path, binding, association_review

    def test_evidence_pack_cli_includes_root_and_two_candidate_levels(self):
        saved, graph, route = self.evidence_fixture()
        result = self.evidence_pack(route["id"])
        packet = json.loads(result.stdout)
        self.assertEqual(packet["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(packet["extractor_identity"], graph["extractor_identity"])
        self.assertEqual(packet["route"]["http_method"], "POST")
        self.assertEqual(packet["route"]["route"], "api/customer/save")
        self.assertEqual(packet["root"]["action_method_name"], "Save")
        root_text = "\n".join(item["text"] for item in packet["source_snippets"])
        self.assertIn("handler.Handle()", root_text)
        methods = {method["method_name"] for bundle in packet["candidate_bundles"]
                   for injection in bundle["injection_candidates"] for registration in injection["registrations"]
                   for candidate in registration["implementation_candidates"] for method in candidate["methods"]}
        nested = {method["method_name"] for bundle in packet["candidate_bundles"]
                  for injection in bundle["injection_candidates"] for registration in injection["registrations"]
                  for candidate in registration["implementation_candidates"] for method in candidate["methods"]
                  for call in method.get("invocations", []) for nested_injection in call["injection_candidates"]
                  for nested_registration in nested_injection["registrations"] for nested_candidate in nested_registration["implementation_candidates"]
                  for nested_method in nested_candidate["methods"] for method in [nested_method]}
        self.assertIn("Handle", methods)
        self.assertEqual(nested, {"SaveAsync", "GetAsync"})
        self.assertTrue(packet["selection"]["complete"])
        self.assertEqual(packet["selection"]["omitted_candidate_bundles"], 0)
        self.assertTrue(all(item["sha256"] and item["span"]["offset_unit"] == "unicode_codepoint"
                            for item in packet["source_snippets"] + packet["candidate_snippets"]))
        cap = len(result.stdout.encode("ascii")) // 2
        bounded = json.loads(self.evidence_pack(route["id"], cap).stdout)
        self.assertEqual(bounded["selection"]["included_candidate_bundles"], 0)
        self.assertEqual(bounded["selection"]["omitted_candidate_bundles"], 1)
        self.assertFalse(bounded["selection"]["complete"])

    def test_evidence_pack_adds_source_backed_bare_same_owner_helpers_once(self):
        source = self.repo / "Flow.cs"
        source.write_text('''namespace Demo;
[Route("api/customer")]
class CustomerController(IHandler handler)
{
    [HttpPost("payment")] void Payment() { handler.Handle(); }
}
class Handler(IStore store, DbContext dbContext)
{
    void Handle() { ApplyDiscountForPaymentAsync(); Other.OnlyDecoy(); new OnlyDecoy(); var text = "OnlyDecoy()"; // OnlyDecoy()
    }
    void ApplyDiscountForPaymentAsync() { if (true) dbContext.SaveChangesAsync(); }
    void ApplyDiscountForPaymentAsync(int amount) { dbContext.SaveChangesAsync(); }
    void OnlyDecoy() { }
}
class Store { void Ping() { } }
class Registrations { void Add() { services.AddScoped<IHandler, Handler>(); services.AddScoped<IStore, Store>(); } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "Flow.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f.get("kind") == "route_action")
        packet = json.loads(self.evidence_pack(route["id"]).stdout)
        method = next(method for bundle in packet["candidate_bundles"] for injection in bundle["injection_candidates"]
                      for registration in injection["registrations"] for candidate in registration["implementation_candidates"]
                      for method in candidate["methods"] if method["method_name"] == "Handle")
        helpers = method["local_helper_candidates"]
        self.assertEqual([helper["call_name"] for helper in helpers], ["ApplyDiscountForPaymentAsync"])
        self.assertFalse(helpers[0]["traversable"])
        self.assertFalse(helpers[0]["bound"])
        self.assertFalse(helpers[0]["reachable"])
        helper_methods = method["local_helper_methods"]
        self.assertEqual(len(helper_methods), 2)  # Both same-owner overloads remain candidates.
        snippet_by_id = {snippet["fact_id"]: snippet for snippet in packet["candidate_snippets"]}
        for helper in helper_methods:
            self.assertIn(helper["method_fact_id"], snippet_by_id)
            self.assertIn("SaveChangesAsync", snippet_by_id[helper["method_fact_id"]]["text"])
            save_calls = [call for call in helper["invocations"] if call["member_name"] == "SaveChangesAsync"]
            self.assertEqual(len(save_calls), 1)
            self.assertIn(save_calls[0]["invocation_fact_id"], snippet_by_id)
            self.assertEqual(snippet_by_id[save_calls[0]["invocation_fact_id"]]["text"], "dbContext.SaveChangesAsync()")
        self.assertNotIn("OnlyDecoy", {helper["call_name"] for helper in helpers})
        full_size = len(self.evidence_pack(route["id"]).stdout.encode("ascii"))
        capped = json.loads(self.evidence_pack(route["id"], full_size // 2).stdout)
        self.assertFalse(capped["selection"]["complete"])
        self.assertEqual(capped["candidate_bundles"], [])
        self.assertEqual(capped["candidate_snippets"], [])

    def test_evidence_pack_no_helper_packet_has_no_new_helper_fields(self):
        _saved, _graph, route = self.evidence_fixture()
        packet = json.loads(self.evidence_pack(route["id"]).stdout)
        for bundle in packet["candidate_bundles"]:
            for injection in bundle["injection_candidates"]:
                for registration in injection["registrations"]:
                    for candidate in registration["implementation_candidates"]:
                        for method in candidate["methods"]:
                            self.assertNotIn("local_helper_candidates", method)
                            self.assertNotIn("local_helper_methods", method)

    def test_evidence_pack_refuses_stale_unknown_wrong_kind_and_mandatory_over_cap(self):
        _saved, graph, route = self.evidence_fixture()
        stale = self.repo / "Flow.cs"
        stale.write_text(stale.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")
        result = self.evidence_pack(route["id"], expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", result.stderr)

        # Restore the saved checkout identity by indexing the new bytes; IDs remain deterministic only for these bytes.
        git(self.repo, "add", "--", "Flow.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f["kind"] == "route_action")
        unknown = self.evidence_pack("unknown-route-fact", expect=2)
        self.assertIn("unknown route fact ID", unknown.stderr)
        wrong = next(f["id"] for f in graph["facts"] if f["kind"] == "type_declaration")
        wrong_result = self.evidence_pack(wrong, expect=2)
        self.assertIn("wrong kind", wrong_result.stderr)
        capped = self.evidence_pack(route["id"], 100, expect=2)
        self.assertEqual(capped.stdout, "")
        self.assertIn("complete mandatory evidence pack requires", capped.stderr)

    def test_route_find_returns_structured_unmapped_evidence_pack_step(self):
        saved, graph, route = self.evidence_fixture()
        result = self.route_find(route["id"])
        document = json.loads(result.stdout)
        self.assertEqual(document["result"], "unmapped")
        self.assertEqual(document["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(document["association_count"], 0)
        self.assertEqual(document["next_step"]["command"], "evidence-pack")
        self.assertEqual(document["next_step"]["arguments"]["--route-fact-id"], route["id"])
        exact = self.route_find(http_method=route["http_method"], route=route["route_literal"])
        self.assertEqual(exact.stdout, result.stdout)

    def test_route_find_exact_selector_shape_and_literal_matching(self):
        _saved, _graph, route = self.evidence_fixture()
        for selector in (
            (),
            ("--http-method", route["http_method"]),
            ("--route", route["route_literal"]),
            ("--route-fact-id", route["id"], "--http-method", route["http_method"], "--route", route["route_literal"]),
            ("--http-method", "", "--route", route["route_literal"]),
            ("--http-method", route["http_method"], "--route", ""),
            ("--route-fact-id", ""),
        ):
            result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                              *selector, "--max-tokens", "10000", expect=2)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr.strip())

        for method, literal in ((route["http_method"].lower(), route["route_literal"]),
                                (route["http_method"], f" {route['route_literal']}")):
            result = self.route_find(http_method=method, route=literal, expect=2)
            self.assertEqual(result.stdout, "")
            self.assertIn("no route_action matches the exact saved method and route", result.stderr)
            if method == route["http_method"].lower():
                self.assertIn("current coverage output", result.stderr)

    def test_route_find_exact_selector_refuses_malformed_saved_facts(self):
        saved, _graph, route = self.evidence_fixture()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute(
                "SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)
            ).fetchone()
            original = json.loads(row[0])
            malformed_variants = ("missing", None, {}, [{"kind": "route_action"}, None])
            for malformed in malformed_variants:
                snapshot = json.loads(json.dumps(original))
                if malformed == "missing":
                    snapshot["source_graph"].pop("facts", None)
                else:
                    snapshot["source_graph"]["facts"] = malformed
                connection.execute(
                    "UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?",
                    (json.dumps(snapshot), saved["snapshot_id"]),
                )
                connection.commit()
                result = self.route_find(http_method=route["http_method"], route=route["route_literal"], expect=2)
                self.assertEqual(result.stdout, "")
                self.assertIn("saved source graph facts must be a list of objects", result.stderr)

    def test_route_find_exact_selector_refuses_duplicate_saved_method_and_route(self):
        source = self.repo / "Duplicates.cs"
        source.write_text('''[Route("api/duplicate")]
class DuplicateController
{
    [HttpGet("same")] void First() {}
    [HttpGet("same")] void Second() {}
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Duplicates.cs")
        _saved, graph, _routes = self.coverage_fixture(count=0)
        duplicate_routes = [fact for fact in graph["facts"] if fact["kind"] == "route_action"]
        self.assertEqual(len(duplicate_routes), 2)
        first = duplicate_routes[0]
        result = self.route_find(http_method=first["http_method"], route=first["route_literal"], expect=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("2 route_action facts match", result.stderr)
        self.assertIn("--route-fact-id", result.stderr)

    def test_route_binding_is_immutable_and_route_find_returns_complete_fresh_claims(self):
        saved, graph, route = self.evidence_fixture()
        attached, flow_receipt = self.reviewed_route_map(saved, graph, route)
        path, binding, association_review = self.route_binding_document(saved, graph, route, attached, flow_receipt)
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", "wrong-snapshot", "--input", os.fspath(path), expect=2)
        path.write_text(json.dumps({"binding": {**binding, "binding_hash": association_review["binding_hash"]},
                                   "association_review": association_review}), encoding="utf-8")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path), expect=2)
        path.write_text(json.dumps({"binding": binding, "association_review": association_review}), encoding="utf-8")
        first = json.loads(self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path)).stdout)
        repeated = json.loads(self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path)).stdout)
        self.assertEqual(first, repeated)
        self.assertEqual(first["binding"]["route_fact_id"], route["id"])
        self.assertNotIn("binding_hash", first["binding"])

        found_result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                "--route-fact-id", route["id"], "--max-tokens", "10000")
        found = json.loads(found_result.stdout)
        self.assertEqual(found["result"], "fresh")
        self.assertEqual(found["association_count"], 1)
        self.assertEqual(found["association"]["binding"], binding)
        self.assertEqual(found["association"]["association_review"]["binding_hash"], association_review["binding_hash"])
        self.assertEqual(found["claim_selection"]["omitted_claims"], 0)
        self.assertEqual(found["claim_selection"]["included_claims"], found["claim_selection"]["total_claims"])
        self.assertEqual(len(found["claims"]), 1)
        exact = self.route_find(http_method=route["http_method"], route=route["route_literal"])
        exact_document = json.loads(exact.stdout)
        id_document = json.loads(found_result.stdout)
        exact_checked_at = exact_document["freshness"].pop("checked_at")
        id_checked_at = id_document["freshness"].pop("checked_at")
        self.assertTrue(exact_checked_at)
        self.assertTrue(id_checked_at)
        self.assertEqual(exact_document, id_document)
        self.assertEqual(exact_document["budget"]["stdout_bytes_including_newline"], len(exact.stdout.encode("ascii")))
        self.assertEqual(id_document["budget"]["stdout_bytes_including_newline"], len(found_result.stdout.encode("ascii")))
        self.assertEqual(len(exact.stdout.encode("ascii")), len(found_result.stdout.encode("ascii")))
        generous_size = len(found_result.stdout.encode("ascii"))
        self.assertEqual(found["budget"]["stdout_bytes_including_newline"], generous_size)
        # The limit itself is rendered in the document, so changing it can change
        # the output length by a digit. Compute the exact boundary for its own cap.
        exact_size = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                              "--route-fact-id", route["id"], "--max-tokens", str(generous_size)).stdout
        exact_size = len(exact_size.encode("ascii"))
        exact = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                         "--route-fact-id", route["id"], "--max-tokens", str(exact_size))
        self.assertEqual(len(exact.stdout.encode("ascii")), exact_size)
        short = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                         "--route-fact-id", route["id"], "--max-tokens", str(exact_size - 1), expect=2)
        self.assertEqual(short.stdout, "")
        self.assertIn("complete route-find output requires", short.stderr)
        exact_short = self.route_find(http_method=route["http_method"], route=route["route_literal"],
                                      max_tokens=exact_size - 1, expect=2)
        self.assertEqual(exact_short.stdout, "")
        self.assertIn("complete route-find output requires", exact_short.stderr)

        conflict = dict(association_review, review_basis="A conflicting association review cannot replace the immutable record.")
        path.write_text(json.dumps({"binding": binding, "association_review": conflict}), encoding="utf-8")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path), expect=2)

    def test_route_find_requires_unique_current_snapshot_and_refuses_stale_sources(self):
        saved, graph, route = self.evidence_fixture()
        routes = self.repo / "Flow.cs"
        routes.write_text(routes.read_text(encoding="utf-8") + "// changed after capture\n", encoding="utf-8")
        stale = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                         "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale.stderr)
        stale_exact = self.route_find(http_method=route["http_method"], route=route["route_literal"], expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale_exact.stderr)
        stale_coverage = self.coverage(expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", stale_coverage.stderr)

        git(self.repo, "add", "--", "Flow.cs")
        current = self.index()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT snapshot_id, payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (current["snapshot_id"],)).fetchone()
            snapshot = json.loads(row[1])
            snapshot["source_graph"]["extractor_identity"] = "obsolete-extractor"
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(snapshot), row[0]))
        old_only = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                            "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", old_only.stderr)
        old_coverage = self.coverage(expect=2)
        self.assertIn("no_saved_snapshot_matches_current_extractor_and_checkout", old_coverage.stderr)

        # Restore one current snapshot and insert a second distinct current row for the same live checkout.
        duplicate_id = current["snapshot_id"] + "-second"
        with sqlite3.connect(self.db) as connection:
            snapshot["source_graph"]["extractor_identity"] = graph["extractor_identity"]
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(snapshot), current["snapshot_id"]))
            duplicate = dict(snapshot, snapshot_id=duplicate_id)
            connection.execute("INSERT INTO atlas_snapshots(snapshot_id, evidence_fingerprint, captured_at, payload_json) VALUES (?, ?, ?, ?)",
                               (duplicate_id, duplicate["evidence_fingerprint"] + "-second", duplicate["captured_at"], json.dumps(duplicate)))
        multiple = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                            "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("multiple_saved_snapshots_match_current_extractor_and_checkout", multiple.stderr)
        multiple_coverage = self.coverage(expect=2)
        self.assertIn("multiple_saved_snapshots_match_current_extractor_and_checkout", multiple_coverage.stderr)

    def test_route_find_requires_valid_bindings_and_requires_selection_for_multiple_maps(self):
        saved, graph, route = self.evidence_fixture()
        first_flow, first_receipt = self.reviewed_route_map(saved, graph, route, "Map one")
        first_path, _first_binding, _first_review = self.route_binding_document(saved, graph, route, first_flow, first_receipt, "first")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(first_path))
        second_flow, second_receipt = self.reviewed_route_map(saved, graph, route, "Map two")
        second_path, _second_binding, _second_review = self.route_binding_document(saved, graph, route, second_flow, second_receipt, "second")
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(second_path))
        multiple_result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                   "--route-fact-id", route["id"], "--max-tokens", "30000")
        multiple = json.loads(multiple_result.stdout)
        self.assertEqual(multiple["result"], "selection_required")
        self.assertEqual(len(multiple["associations"]), 2)
        self.assertNotIn("claims", multiple)
        exact_multiple = self.route_find(http_method=route["http_method"], route=route["route_literal"], max_tokens=30000)
        self.assertEqual(exact_multiple.stdout, multiple_result.stdout)

        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_route_bindings WHERE overlay_id = ?", (first_flow["overlay_id"],)).fetchone()
            tampered = json.loads(row[0])
            tampered["binding"]["overlay_id"] = second_flow["overlay_id"]
            connection.execute("UPDATE atlas_route_bindings SET payload_json = ? WHERE overlay_id = ?",
                               (json.dumps(tampered), first_flow["overlay_id"]))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "30000", expect=2)
        self.assertIn("payload does not match its registry key", refused.stderr)
        coverage_refused = self.coverage(expect=2)
        self.assertIn("payload does not match its registry key", coverage_refused.stderr)

    def test_route_find_refuses_binding_with_tampered_route_registry_key(self):
        saved, graph, route = self.evidence_fixture()
        attached, flow_receipt = self.reviewed_route_map(saved, graph, route)
        path, _binding, _review = self.route_binding_document(saved, graph, route, attached, flow_receipt)
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path))
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_route_bindings SET route_fact_id = ? WHERE snapshot_id = ? AND route_fact_id = ?",
                               ("tampered-route-key", saved["snapshot_id"], route["id"]))
        result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                          "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("registry key", result.stderr)
        self.assertIn("registry key", self.coverage(expect=2).stderr)

        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_route_bindings SET route_fact_id = ? WHERE snapshot_id = ?",
                               (route["id"], saved["snapshot_id"]))
        with sqlite3.connect(self.db) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("UPDATE atlas_route_bindings SET snapshot_id = ? WHERE route_fact_id = ?",
                               ("tampered-snapshot-key", route["id"]))
        result = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                          "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("registry key", result.stderr)

    def test_route_refresh_carries_complete_route_map_through_all_consumers(self):
        saved, _graph, route, attached, reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        self.index()
        refreshed = json.loads(self.route_refresh(saved, route).stdout)
        target = refreshed["snapshot_id"]
        self.assertEqual(refreshed["result"], "carried")
        self.assertEqual(refreshed["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])
        self.assertEqual(refreshed["carry_provenance"]["origin_overlay_id"], attached["overlay_id"])
        self.assertEqual(refreshed["carry_provenance"]["origin_review_receipt_hash"], reviewed["receipt_hash"])

        found = json.loads(self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                    "--route-fact-id", route["id"], "--max-tokens", "100000").stdout)
        self.assertEqual(found["snapshot_id"], target)
        self.assertEqual(found["overlay_id"], attached["overlay_id"])
        self.assertEqual(found["claim_selection"]["included_claims"], 8)
        self.assertEqual(found["claim_selection"]["omitted_claims"], 0)
        self.assertEqual(found["reviewer"]["identity"], "fixture reviewer")
        self.assertEqual(found["reviewer"]["reviewed_at"], "2026-10-06T12:00:00Z")
        for field, value in refreshed["carry_provenance"].items():
            self.assertEqual(found["carry_provenance"][field], value)

        focus = json.loads(self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                    "--snapshot", target, "--overlay", attached["overlay_id"],
                                    "--max-tokens", "100000").stdout)
        self.assertEqual(focus["snapshot_id"], target)
        self.assertEqual(focus["claim_selection"]["included_claims"], 8)
        self.assertEqual(focus["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])
        flow = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", target,
                                   "--overlay", attached["overlay_id"]).stdout)
        self.assertEqual(flow["snapshot_id"], target)
        self.assertEqual(flow["review_status"], "accepted")
        self.assertEqual(flow["review_receipt"]["receipt_hash"], reviewed["receipt_hash"])
        self.assertEqual(flow["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])

        question, draft = self.root / "question.txt", self.root / "draft.txt"
        question.write_text("What does this reviewed route map say?", encoding="utf-8")
        draft.write_text("The reviewed map contains eight route claims.", encoding="utf-8")
        answer_args = ("answer-check", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                       "--snapshot", target, "--overlay", attached["overlay_id"],
                       "--question-file", os.fspath(question), "--draft-file", os.fspath(draft))
        packet = json.loads(self.cli(*answer_args).stdout)
        self.assertEqual(packet["binding"]["snapshot_id"], target)
        self.assertEqual(packet["binding"]["overlay_id"], attached["overlay_id"])
        self.assertEqual(packet["review_provenance"]["reviewer"]["identity"], "fixture reviewer")
        self.assertEqual(packet["review_provenance"]["review_receipt_hash"], reviewed["receipt_hash"])
        self.assertEqual(packet["review_provenance"]["carry_provenance"]["origin_snapshot_id"], saved["snapshot_id"])
        self.assertEqual(len(packet["claims"]), 8)
        answer_review = {"packet_sha256": hashlib.sha256(json.dumps(packet, ensure_ascii=True, sort_keys=True,
                                separators=(",", ":")).encode("ascii") + b"\n").hexdigest(),
                         "decision": "accepted", "reviewer_identity": "answer reviewer", "reviewer_model": "GPT-6.1 Sol High",
                         "claim_reviews": [{"claim_number": index, "disposition": "covered",
                                            "basis": "The draft covers the complete claim set in this fixture."}
                                           for index in range(1, 9)]}
        answer_review_path = self.root / "answer.review.json"
        answer_review_path.write_text(json.dumps(answer_review), encoding="utf-8")
        accepted = self.cli(*answer_args, "--review", os.fspath(answer_review_path))
        self.assertEqual(accepted.stdout.encode("utf-8"), draft.read_bytes())

        repeated = json.loads(self.route_refresh(saved, route).stdout)
        self.assertEqual(repeated, refreshed)

    def test_route_refresh_refuses_changed_route_handler(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        source = self.repo / "Handler.cs"
        source.write_text(source.read_text(encoding="utf-8").replace("store.SaveAsync(); store.GetAsync();",
                                                                    "store.GetAsync(); store.SaveAsync();"), encoding="utf-8")
        current = self.index()
        target_routes = [fact for fact in self.graph(current["snapshot_id"])["facts"] if fact.get("id") == route["id"]]
        self.assertEqual(target_routes, [route])
        refused = self.route_refresh(saved, route, expect=2)
        self.assertIn("cited source hash changed", refused.stderr)
        with sqlite3.connect(self.db) as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_route_carries'").fetchone()
            count = connection.execute("SELECT COUNT(*) FROM atlas_route_carries").fetchone()[0] if exists else 0
        self.assertEqual(count, 0)

    def test_route_refresh_refuses_unchanged_origin_without_poisoning_review(self):
        saved, _graph, route, attached, _reviewed = self.refresh_fixture()
        refused = self.route_refresh(saved, route, expect=2)
        self.assertIn("target equals the accepted origin", refused.stderr)
        found = json.loads(self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                                    "--route-fact-id", route["id"], "--max-tokens", "100000").stdout)
        self.assertEqual(found["overlay_id"], attached["overlay_id"])
        self.assertEqual(found["claim_selection"]["included_claims"], 8)

    def test_route_refresh_refuses_change_just_before_commit(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        other = self.repo / "Other.cs"
        other.write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        handler = self.repo / "Handler.cs"
        spec = importlib.util.spec_from_file_location("atlas_refresh_race_test", SCRIPT)
        atlas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(atlas)
        original_connect = atlas._connect_for_index

        def change_at_connect(path):
            handler.write_text(handler.read_text(encoding="utf-8").replace("store.SaveAsync(); store.GetAsync();",
                                                                              "store.GetAsync(); store.SaveAsync();"), encoding="utf-8")
            return original_connect(path)

        with mock.patch.object(sys, "path", [os.fspath(SCRIPT.parent), *sys.path]), mock.patch.object(
                atlas, "_connect_for_index", side_effect=change_at_connect):
            with self.assertRaisesRegex(atlas.AtlasError, "changed before route refresh commit"):
                atlas.route_refresh(os.fspath(self.db), os.fspath(self.repo), saved["snapshot_id"], route["id"], 100000)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM atlas_snapshots").fetchone()[0], 1)
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_route_carries'").fetchone()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM atlas_route_carries").fetchone()[0] if exists else 0, 0)

    def test_route_refresh_refuses_new_candidate_declaration_and_registration(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        extra = self.repo / "ExtraCandidate.cs"
        extra.write_text("class Handler { void Handle() {} }\n", encoding="utf-8")
        git(self.repo, "add", "--", "ExtraCandidate.cs")
        self.index()
        declaration_refusal = self.route_refresh(saved, route, expect=2)
        self.assertIn("evidence packet changed", declaration_refusal.stderr)

    def test_route_refresh_refuses_new_matching_registration(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        registration = self.repo / "Other.cs"
        registration.write_text("class Other { int Read() { return 1; } }\nclass ExtraHandler { void Handle() {} }\n"
                                "class MoreRegistrations { void Add() { services.AddScoped<IHandler, ExtraHandler>(); } }\n", encoding="utf-8")
        git(self.repo, "add", "--", "Other.cs")
        self.index()
        registration_refusal = self.route_refresh(saved, route, expect=2)
        self.assertIn("evidence packet changed", registration_refusal.stderr)

    def test_route_refresh_refuses_tampered_origin_review_provenance(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        self.index()
        refreshed = json.loads(self.route_refresh(saved, route).stdout)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_flow_reviews SET receipt_json = replace(receipt_json, 'fixture reviewer', 'tampered reviewer') WHERE snapshot_id=?",
                               (saved["snapshot_id"],))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "100000", expect=2)
        self.assertIn("review receipt content hash is invalid", refused.stderr)
        self.assertEqual(refreshed["result"], "carried")

    def test_route_refresh_refuses_tampered_carry_overlay_identity(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        self.route_refresh(saved, route)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_route_carries SET origin_overlay_id = ?", ("wrong-overlay",))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "100000", expect=2)
        self.assertIn("registry identity differs", refused.stderr)

    def test_route_refresh_rolls_back_target_snapshot_when_carry_insert_fails(self):
        saved, _graph, route, _attached, _reviewed = self.refresh_fixture()
        (self.repo / "Other.cs").write_text("class Other { int Read() { return 2; } }\n", encoding="utf-8")
        too_small = self.route_refresh(saved, route, expect=2, max_tokens=1)
        self.assertIn("complete route-find output requires", too_small.stderr)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM atlas_snapshots").fetchone()[0], 1)
        with sqlite3.connect(self.db) as connection:
            connection.execute("""CREATE TABLE atlas_route_carries (
                target_snapshot_id TEXT NOT NULL, route_fact_id TEXT NOT NULL, overlay_id TEXT NOT NULL,
                origin_snapshot_id TEXT NOT NULL, origin_overlay_id TEXT NOT NULL, origin_receipt_hash TEXT NOT NULL,
                binding_hash TEXT NOT NULL, association_review_hash TEXT NOT NULL, packet_sha256 TEXT NOT NULL,
                PRIMARY KEY(target_snapshot_id, route_fact_id))""")
            connection.execute("CREATE TRIGGER refuse_route_carry BEFORE INSERT ON atlas_route_carries BEGIN SELECT RAISE(ABORT, 'test carry failure'); END")
        refused = self.route_refresh(saved, route, expect=2)
        self.assertIn("test carry failure", refused.stderr)
        with sqlite3.connect(self.db) as connection:
            snapshots = connection.execute("SELECT snapshot_id FROM atlas_snapshots ORDER BY snapshot_id").fetchall()
            carries = connection.execute("SELECT COUNT(*) FROM atlas_route_carries").fetchone()[0]
        self.assertEqual([row[0] for row in snapshots], [saved["snapshot_id"]])
        self.assertEqual(carries, 0)

    def test_route_find_refuses_flow_receipt_column_tampering(self):
        saved, graph, route = self.evidence_fixture()
        attached, flow_receipt = self.reviewed_route_map(saved, graph, route)
        path, _binding, _review = self.route_binding_document(saved, graph, route, attached, flow_receipt)
        self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path))
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_flow_reviews SET receipt_hash = ? WHERE snapshot_id = ? AND overlay_id = ?",
                               ("0" * 64, saved["snapshot_id"], attached["overlay_id"]))
        refused = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                           "--route-fact-id", route["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("flow review receipt registry hash", refused.stderr)
        exact_refused = self.route_find(http_method=route["http_method"], route=route["route_literal"], expect=2)
        self.assertIn("flow review receipt registry hash", exact_refused.stderr)
        self.assertIn("flow review receipt registry hash", self.coverage(expect=2).stderr)

    def test_coverage_pages_all_routes_once_with_global_counts_and_exact_byte_boundary(self):
        saved, graph, routes = self.coverage_fixture()
        self.assertEqual(len(routes), 6)
        too_small = self.coverage(max_tokens=1, expect=2)
        self.assertEqual(too_small.stdout, "")
        required = int(too_small.stderr.split("requires ", 1)[1].split(" ASCII", 1)[0])
        adjusted = self.coverage(max_tokens=required, expect=2)
        required = int(adjusted.stderr.split("requires ", 1)[1].split(" ASCII", 1)[0])
        boundary = self.coverage(max_tokens=required)
        first = json.loads(boundary.stdout)
        self.assertEqual(first["snapshot"]["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(first["snapshot"]["extractor_identity"], graph["extractor_identity"])
        self.assertEqual(first["current_checkout"]["repository_root"], os.fspath(self.repo.resolve()))
        self.assertEqual(len(first["routes"]), 1)
        self.assertEqual(first["included_routes"], 1)
        self.assertEqual(first["remaining_routes"], 5)
        self.assertEqual(first["next_offset"], 1)
        self.assertEqual(first["budget"]["stdout_bytes_including_newline"], len(self.coverage(max_tokens=required).stdout.encode("ascii")))
        one_short = self.coverage(max_tokens=required - 1, expect=2)
        self.assertEqual(one_short.stdout, "")
        self.assertIn(f"requires {required} ASCII stdout bytes", one_short.stderr)

        seen = [row["route_fact_id"] for row in first["routes"]]
        page = first
        while page["next_offset"] is not None:
            page_offset = page["next_offset"]
            page_result = self.coverage(max_tokens=required + 10, offset=page_offset, expect=None)
            if page_result.returncode:
                page_required = int(page_result.stderr.split("requires ", 1)[1].split(" ASCII", 1)[0])
                page_result = self.coverage(max_tokens=page_required + 10, offset=page_offset)
            page = json.loads(page_result.stdout)
            seen.extend(row["route_fact_id"] for row in page["routes"])
        self.assertEqual(seen, [route["id"] for route in routes])
        self.assertEqual(len(set(seen)), len(routes))
        self.assertEqual(first["counts"], {"open": 6, "one_reviewed_link": 0, "selection_required": 0, "total_routes": 6})
        eof = json.loads(self.coverage(max_tokens=required, offset=len(routes)).stdout)
        self.assertEqual(eof["routes"], [])
        self.assertIsNone(eof["next_offset"])
        self.assertEqual(eof["remaining_routes"], 0)
        self.assertEqual(self.coverage(max_tokens=required, offset=len(routes) + 1, expect=2).stdout, "")
        self.assertEqual(self.coverage(max_tokens=required, offset=-1, expect=2).stdout, "")

    def test_coverage_reports_open_single_and_multiple_reviewed_associations(self):
        saved, graph, routes = self.coverage_fixture(count=3)
        for route, suffix in ((routes[1], "single"), (routes[2], "multiple-a"), (routes[2], "multiple-b")):
            attached, receipt = self.reviewed_route_map(saved, graph, route, f"Coverage {suffix}")
            path, _binding, _review = self.route_binding_document(saved, graph, route, attached, receipt, f"coverage-{suffix}")
            self.cli("route-bind-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(path))
        document = json.loads(self.coverage().stdout)
        self.assertEqual(document["counts"], {"open": 1, "one_reviewed_link": 1, "selection_required": 1, "total_routes": 3})
        by_id = {row["route_fact_id"]: row for row in document["routes"]}
        self.assertEqual(by_id[routes[0]["id"]]["association_state"], "open")
        self.assertEqual(by_id[routes[1]["id"]]["reviewed_association_count"], 1)
        self.assertEqual(by_id[routes[2]["id"]]["association_state"], "selection_required")
        self.assertEqual(by_id[routes[2]["id"]]["reviewed_association_count"], 2)

    def test_coverage_accepts_missing_binding_table_and_zero_routes(self):
        self.index()
        no_routes = json.loads(self.coverage().stdout)
        self.assertEqual(no_routes["counts"]["total_routes"], 0)
        self.assertEqual(no_routes["routes"], [])
        self.assertIsNone(no_routes["next_offset"])

        # A fresh database has no binding registry table; all saved routes remain open.
        self.db = self.root / "no-bindings.sqlite"
        _saved, _graph, routes = self.coverage_fixture(count=2)
        result = json.loads(self.coverage().stdout)
        self.assertEqual(result["counts"]["open"], len(routes))

    def test_coverage_rejects_corrupt_route_metadata(self):
        saved, _graph, routes = self.coverage_fixture(count=2)
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            snapshot = json.loads(row[0])
            route = next(fact for fact in snapshot["source_graph"]["facts"] if fact.get("id") == routes[0]["id"])
            route["action_name"] = None
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(snapshot), saved["snapshot_id"]))
        refused = self.coverage(expect=2)
        self.assertIn("invalid action_name", refused.stderr)

    def test_coverage_rejects_nonstring_and_duplicate_route_ids(self):
        saved, _graph, routes = self.coverage_fixture(count=2)
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            original = json.loads(row[0])
        for mutate, expected in (
            (lambda snapshot: next(fact for fact in snapshot["source_graph"]["facts"] if fact.get("id") == routes[0]["id"]).update({"id": 7}), "non-string or empty id"),
            (lambda snapshot: next(fact for fact in snapshot["source_graph"]["facts"] if fact.get("id") == routes[1]["id"]).update({"id": routes[0]["id"]}), "ID is duplicated"),
        ):
            changed = json.loads(json.dumps(original))
            mutate(changed)
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(changed), saved["snapshot_id"]))
            self.assertIn(expected, self.coverage(expect=2).stderr)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(original), saved["snapshot_id"]))

    def test_coverage_rejects_missing_or_malformed_fact_lists_and_cross_kind_id_collisions(self):
        saved, _graph, routes = self.coverage_fixture(count=2)
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            original = json.loads(row[0])
        graph_original = original["source_graph"]

        for graph, expected in (
            ({key: value for key, value in graph_original.items() if key != "facts"}, "facts must be a list of objects"),
            ({**graph_original, "facts": {}}, "facts must be a list of objects"),
            ({**graph_original, "facts": [*graph_original["facts"], "not-a-fact"]}, "facts must be a list of objects"),
        ):
            changed = json.loads(json.dumps(original))
            changed["source_graph"] = graph
            with sqlite3.connect(self.db) as connection:
                connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(changed), saved["snapshot_id"]))
            self.assertIn(expected, self.coverage(expect=2).stderr)

        changed = json.loads(json.dumps(original))
        changed["source_graph"]["facts"].append({"id": routes[0]["id"], "kind": "type_declaration"})
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(changed), saved["snapshot_id"]))
        self.assertIn("not unique across source graph facts", self.coverage(expect=2).stderr)
        ambiguous = self.cli("route-find", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                             "--route-fact-id", routes[0]["id"], "--max-tokens", "10000", expect=2)
        self.assertIn("wrong kind or is ambiguous", ambiguous.stderr)

        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(original), saved["snapshot_id"]))

    def test_evidence_pack_preserves_registration_ambiguity_and_shadowing(self):
        _saved, graph, route = self.evidence_fixture(
            extra_registration="services.AddTransient<IHandler, OtherHandler>();", shadow=True,
        )
        packet = json.loads(self.evidence_pack(route["id"]).stdout)
        handler_call = packet["candidate_bundles"][0]
        injection = handler_call["injection_candidates"][0]
        self.assertEqual(injection["registration_match_count"], 2)
        self.assertEqual(len(injection["registrations"]), 2)
        reasons = [item["reason"] for call in handler_call["injection_candidates"][0]["registrations"][0]
                   ["implementation_candidates"][0]["methods"][0]["invocations"] for item in call["unresolved"]]
        self.assertTrue(any("shadow" in reason for reason in reasons))
        self.assertTrue(all(candidate.get("traversable") is False
                            for registration in injection["registrations"]
                            for candidate in registration["implementation_candidates"]))

    def test_evidence_pack_excludes_sibling_action_authorization(self):
        source = self.repo / "Auth.cs"
        source.write_text('''[Authorize]
[Route("api/auth")]
class AuthController
{
    [HttpPost("admin/login")]
    [Authorize(Policy = "Login")]
    void AdminLogin() {}

    [HttpPost("admin/logout")]
    [Authorize(Policy = "Logout")]
    void AdminLogout() {}
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Auth.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(f for f in graph["facts"] if f.get("kind") == "route_action" and f.get("route_literal") == "api/auth/admin/login")
        sibling = next(f for f in graph["facts"] if f.get("kind") == "authorization_attribute" and f.get("method_id")
                       and next(m for m in graph["facts"] if m.get("id") == f["method_id"])["method_name"] == "AdminLogout")
        packet = json.loads(self.evidence_pack(route["id"]).stdout)
        included = set(packet["route"]["authorization_fact_ids"])
        self.assertIn(sibling["owner_type_id"], {route["controller_type_id"]})
        self.assertNotIn(sibling["id"], included)
        self.assertEqual(len(included), 2)  # Controller authorization and AdminLogin authorization.

    def test_evidence_pack_fails_closed_on_missing_implementation_candidate_fact(self):
        saved, graph, route = self.evidence_fixture()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            payload = json.loads(row[0])
            candidate = next(c for c in payload["source_graph"]["candidates"]
                             if c.get("expression_side") == "implementation"
                             and any(f.get("kind") == "dependency_registration" and f["id"] == c["subject_fact_id"]
                                     and f.get("implementation_type_expression") == "Handler"
                                     for f in payload["source_graph"]["facts"]))
            candidate["candidate_fact_ids"] = ["missing-declaration-fact"]
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(payload), saved["snapshot_id"]))
        result = self.evidence_pack(route["id"], expect=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("missing or wrong-kind declaration fact ID", result.stderr)

    def test_evidence_pack_render_stabilizes_byte_count_at_digit_boundary(self):
        spec = importlib.util.spec_from_file_location("atlas_under_test", SCRIPT)
        atlas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(atlas)
        document = {"budget": {"stdout_bytes_including_newline": 0}, "padding": "x" * 9936}
        with self.assertRaises(atlas.AtlasError):
            atlas._evidence_pack_render(document, 10000)
        rendered = atlas._evidence_pack_render(document, 20000)
        self.assertEqual(document["budget"]["stdout_bytes_including_newline"], len(rendered))

    def test_discover_ranks_multiple_routes_and_respects_exact_output_cap(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('''using Microsoft.AspNetCore.Mvc;
namespace Demo;
[ApiController]
[Route("api/customer")]
class PhotoController
{
    [HttpPost("photo/upload")] void UploadPhoto() {}
    [HttpPost("photo/submit-image")] void SubmitImage() {}
}
[Route("api/admin")]
class OtherController
{
    [HttpPost("photo/upload")] void UploadPhoto() {}
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        terms = ["customer", "photo", "upload", "image", "selfie"]

        full = self.discover_routes(terms)
        document = json.loads(full.stdout)
        exact_size = len(full.stdout.encode("ascii"))
        self.assertEqual(document["snapshot_id"], saved["snapshot_id"])
        self.assertEqual(document["result"], "candidates")
        self.assertEqual(document["budget"]["stdout_bytes_including_newline"], exact_size)
        self.assertEqual(document["candidate_selection"], {"included_candidates": 3, "omitted_candidates": 0, "total_candidates": 3})
        self.assertEqual([item["route"] for item in document["candidates"][:2]], ["api/customer/photo/submit-image", "api/customer/photo/upload"])
        self.assertEqual([item["lexical_score"] for item in document["candidates"]], [3, 3, 2])
        for item in document["candidates"]:
            self.assertTrue(item["fact_id"])
            self.assertEqual(set(item["action_source"]), {"fact_id", "path", "sha256", "span"})
            self.assertEqual(set(item["controller_source"]), {"fact_id", "path", "sha256", "span"})
            self.assertTrue(item["action_source"]["span"])
            self.assertTrue(item["controller_source"]["span"])
            self.assertEqual(item["action_source"]["sha256"], item["controller_source"]["sha256"])

        exact = None
        for _ in range(5):
            exact = self.discover_routes(terms, exact_size)
            measured = len(exact.stdout.encode("ascii"))
            if measured == exact_size:
                break
            exact_size = measured
        self.assertIsNotNone(exact)
        self.assertEqual(len(exact.stdout.encode("ascii")), exact_size)
        self.assertEqual(json.loads(exact.stdout)["candidate_selection"]["included_candidates"], 3)
        one_short = self.discover_routes(terms, exact_size - 1)
        shortened = json.loads(one_short.stdout)
        self.assertLessEqual(len(one_short.stdout.encode("ascii")), exact_size - 1)
        self.assertEqual(shortened["candidate_selection"]["omitted_candidates"], 1)
        self.assertEqual(shortened["candidates"], document["candidates"][:2])

        too_small = self.discover_routes(terms, 1, expect=2)
        self.assertEqual(too_small.stdout, "")
        self.assertIn("complete discover output requires", too_small.stderr)
        self.assertIn("stdout withheld", too_small.stderr)

        unmatched = self.discover_routes(["unrelated-term"], 10000)
        unmatched_json = json.loads(unmatched.stdout)
        self.assertEqual(unmatched_json["result"], "no_lexical_matches")
        self.assertEqual(unmatched_json["candidate_selection"]["total_candidates"], 0)
        self.assertEqual(unmatched_json["unmatched_route_count"], 3)

    def test_discover_refuses_same_status_changed_bytes_and_caps_stale_diagnostics(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() {} }\n', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        self.index()

        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() { } }\n', encoding="utf-8")
        first_status = git(self.repo, "status", "--porcelain=v1", "-z")
        first = self.discover_routes(["customer", "photo", "upload"], 10000, expect=3)
        stale = json.loads(first.stdout)
        self.assertEqual(stale["result"], "refused")
        self.assertEqual(stale["candidate_selection"]["total_candidates"], 0)
        self.assertTrue(any("content hash changed" in reason for mismatch in stale["source_mismatches"] for reason in mismatch["reasons"]))
        exact_size = len(first.stdout.encode("ascii"))
        self.assertEqual(stale["budget"]["stdout_bytes_including_newline"], exact_size)

        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto(){} }\n', encoding="utf-8")
        self.assertEqual(git(self.repo, "status", "--porcelain=v1", "-z"), first_status)
        second = self.discover_routes(["customer", "photo", "upload"], exact_size, expect=3)
        second_json = json.loads(second.stdout)
        self.assertLessEqual(len(second.stdout.encode("ascii")), exact_size)
        self.assertEqual(second_json["budget"]["stdout_bytes_including_newline"], len(second.stdout.encode("ascii")))
        short = self.discover_routes(["customer", "photo", "upload"], 1, expect=2)
        self.assertEqual(short.stdout, "")
        self.assertIn("complete discover output requires", short.stderr)
        self.assertIn("stdout withheld", short.stderr)

    def test_discover_refuses_snapshot_with_old_extractor(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() {} }\n', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT payload_json FROM atlas_snapshots WHERE snapshot_id = ?", (saved["snapshot_id"],)).fetchone()
            payload = json.loads(row[0])
            payload["source_graph"]["extractor_identity"] = "csharp-lexical-facts-v6:python-stdlib-lexer"
            connection.execute("UPDATE atlas_snapshots SET payload_json = ? WHERE snapshot_id = ?", (json.dumps(payload), saved["snapshot_id"]))
        result = self.discover_routes(["customer", "photo", "upload"], 10000, expect=3)
        document = json.loads(result.stdout)
        self.assertEqual(document["reason"], "no_saved_snapshot_matches_current_extractor_and_checkout")
        self.assertEqual(document["compatible_snapshot_count"], 0)
        self.assertEqual(document["candidate_selection"]["total_candidates"], 0)

    def test_discover_refuses_multiple_current_snapshot_matches(self):
        routes = self.repo / "Routes.cs"
        routes.write_text('namespace Demo; [Route("api/customer")] class CustomerController { [HttpPost("photo/upload")] void UploadPhoto() {} }\n', encoding="utf-8")
        git(self.repo, "add", "--", "Routes.cs")
        saved = self.index()
        with sqlite3.connect(self.db) as connection:
            row = connection.execute(
                "SELECT captured_at, payload_json FROM atlas_snapshots WHERE snapshot_id = ?",
                (saved["snapshot_id"],),
            ).fetchone()
            payload = json.loads(row[1])
            payload["snapshot_id"] = "atlas-test-duplicate"
            connection.execute(
                "INSERT INTO atlas_snapshots(snapshot_id, evidence_fingerprint, captured_at, payload_json) VALUES (?, ?, ?, ?)",
                (payload["snapshot_id"], "duplicate-evidence-fingerprint", row[0], json.dumps(payload)),
            )
        result = self.discover_routes(["customer", "photo", "upload"], 10000, expect=3)
        document = json.loads(result.stdout)
        self.assertEqual(document["reason"], "multiple_saved_snapshots_match_current_extractor_and_checkout")
        self.assertEqual(len(document["matching_snapshot_ids"]), 2)
        self.assertEqual(document["candidate_selection"]["total_candidates"], 0)

    def test_persists_and_queries_in_separate_process_with_nul_safe_paths(self):
        first = self.index()
        self.assertEqual(first["schema_version"], 2)
        self.assertIsNone(first["head"])
        self.assertTrue(first["head_ref"].startswith("refs/heads/"))
        self.assertEqual(first["inventory_basis"], "git-index-paths+working-tree-bytes")
        self.assertEqual(first["tracked_count"], 2)
        a_file = next(item for item in first["files"] if item["path"] == "a.txt")
        self.assertEqual(a_file["sha256"], hashlib.sha256(b"alpha\x00\n").hexdigest())
        self.assertEqual(a_file["size_bytes"], 7)

        reopened = self.query(first["snapshot_id"])
        self.assertEqual(reopened["files"], first["files"])
        exact = self.query(first["snapshot_id"], "--path", "sub dir/b.txt")
        self.assertEqual(exact["matched_count"], 1)
        self.assertEqual(exact["files"][0]["sha256"], hashlib.sha256(b"beta\n").hexdigest())

    def test_fingerprint_repeats_without_capture_time_and_changes_for_dirty_bytes(self):
        first = self.index()
        repeated = self.index()
        self.assertEqual(first["snapshot_id"], repeated["snapshot_id"])
        self.assertEqual(first["evidence_fingerprint"], repeated["evidence_fingerprint"])
        self.assertEqual(first["captured_at"], repeated["captured_at"])

        (self.repo / "a.txt").write_bytes(b"changed while HEAD stays fixed")
        changed = self.index()
        self.assertNotEqual(changed["snapshot_id"], first["snapshot_id"])
        self.assertNotEqual(changed["evidence_fingerprint"], first["evidence_fingerprint"])
        self.assertIsNone(changed["head"])
        self.assertEqual(changed["head_ref"], first["head_ref"])
        self.assertEqual(self.query(first["snapshot_id"])["files"], first["files"])
        self.assertEqual(self.query(changed["snapshot_id"])["head"], first["head"])

    def test_untracked_files_appear_only_in_status_and_capture_is_repeatable(self):
        (self.repo / "untracked.bin").write_bytes(b"outside inventory")
        snap = self.index()
        self.assertNotIn("untracked.bin", [entry["path"] for entry in snap["files"]])
        self.assertIn("untracked.bin", [entry["path"] for entry in snap["status"]])

    def test_failed_capture_does_not_add_partial_snapshot_and_missing_query_does_not_create_db(self):
        saved = self.index()
        with sqlite3.connect(self.db) as connection:
            before = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        self.cli("index", "--repo", os.fspath(self.root / "not-a-repo"), "--db", os.fspath(self.db), expect=2)
        with sqlite3.connect(self.db) as connection:
            after = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(self.query(saved["snapshot_id"])["snapshot_id"], saved["snapshot_id"])

        absent_db = self.root / "absent.sqlite"
        failed = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), "query", "--db", os.fspath(absent_db), "--snapshot", "missing"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertFalse(absent_db.exists())

    def test_missing_tracked_path_is_explicit(self):
        (self.repo / "a.txt").unlink()
        snap = self.index()
        missing = next(item for item in snap["files"] if item["path"] == "a.txt")
        self.assertEqual(missing["presence"], "missing")
        self.assertIsNone(missing["sha256"])

    def test_intermediate_symlink_is_rejected_and_previous_snapshot_remains_queryable(self):
        saved = self.index()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "b.txt").write_bytes(b"outside secret bytes")
        tracked_parent = self.repo / "sub dir"
        (tracked_parent / "b.txt").unlink()
        tracked_parent.rmdir()
        tracked_parent.symlink_to(outside, target_is_directory=True)

        with sqlite3.connect(self.db) as connection:
            before = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        failure = self.cli(
            "index", "--repo", os.fspath(self.repo), "--db", os.fspath(self.db), expect=2
        )
        self.assertIn("unsafe tracked path 'sub dir/b.txt'", failure.stderr)
        self.assertIn("cannot open parent component 'sub dir'", failure.stderr)
        self.assertNotIn("outside secret bytes", failure.stderr)
        with sqlite3.connect(self.db) as connection:
            after = connection.execute("SELECT count(*) FROM atlas_snapshots").fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(self.query(saved["snapshot_id"])["files"], saved["files"])

    def test_direct_leaf_symlink_is_recorded_without_reading_its_target(self):
        outside = self.root / "outside secret"
        outside.write_bytes(b"must not be read")
        leaf = self.repo / "leaf-link"
        leaf.symlink_to(outside)
        git(self.repo, "add", "--", "leaf-link")

        saved = self.index()
        evidence = next(entry for entry in saved["files"] if entry["path"] == "leaf-link")
        link_bytes = os.fsencode(os.readlink(leaf))
        self.assertEqual(evidence["type"], "symlink")
        self.assertEqual(evidence["size_bytes"], len(link_bytes))
        self.assertEqual(evidence["sha256"], hashlib.sha256(link_bytes).hexdigest())
        self.assertNotEqual(evidence["sha256"], hashlib.sha256(outside.read_bytes()).hexdigest())

    def test_query_database_paths_with_uri_delimiters_and_no_unintended_files(self):
        expected_entries = {"repo"}
        for name in ("question?mark.sqlite", "hash#mark.sqlite", "percent%mark.sqlite"):
            with self.subTest(name=name):
                db = self.root / name
                indexed = json.loads(self.cli(
                    "index", "--repo", os.fspath(self.repo), "--db", os.fspath(db)
                ).stdout)
                queried = json.loads(self.cli(
                    "query", "--db", os.fspath(db), "--snapshot", indexed["snapshot_id"]
                ).stdout)
                self.assertEqual(queried["snapshot_id"], indexed["snapshot_id"])
                expected_entries.add(name)
                self.assertEqual({path.name for path in self.root.iterdir()}, expected_entries)

    def test_missing_database_is_refused_without_creation(self):
        absent_db = self.root / "absent.sqlite"
        failed = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), "query", "--db", os.fspath(absent_db), "--snapshot", "missing"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertIn("database does not exist", failed.stderr)
        self.assertFalse(absent_db.exists())

    def test_source_graph_ignores_decoys_and_keeps_ambiguous_or_shadowed_cases_unresolved(self):
        source = self.repo / "GraphFixture.cs"
        source.write_text(r'''namespace Demo;
interface IHandler<T> {}
class Query {}
class Box<TLeft, TRight> {}
class Handler : IHandler<Box<Query, string>> {}
[Route(@"api/customer")]
class FeedController(IHandler<Box<Query, string>> handler)
{
    [HttpGet("images/\u0061")]
    public void GetImages() { handler.Run(); }
    [HttpPost($"fake/{1}")]
    public void Interpolated() { handler.Fake(); }
    public void Decoys()
    {
        var one = "[HttpPost(\"fake\")] handler.Nope()";
        var two = @"handler.Nope()";
        var three = """handler.Nope()""";
        // [HttpPost("comment")] handler.Nope();
        /* handler.Nope(); */
    }
    public void Shadowed()
    {
        var handler = new Handler();
        handler.Hidden();
    }
}
class Setup
{
    void Configure(IServiceCollection services)
    {
        services.AddScoped<IHandler<Box<Query, string>>, Handler>();
        services.AddScoped<IHandler<Box<Query, string>>, Handler>();
    }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "GraphFixture.cs")

        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(fact for fact in graph["facts"] if fact["kind"] == "route_action" and fact["action_name"] == "GetImages")
        self.assertEqual(route["route_literal"], "api/customer/images/a")
        self.assertEqual(route["source"]["path"], "GraphFixture.cs")
        self.assertGreater(route["source"]["span"]["end_offset"], route["source"]["span"]["start_offset"])

        calls = [fact for fact in graph["facts"] if fact["kind"] == "receiver_invocation_syntax" and fact["source"]["path"] == "GraphFixture.cs"]
        self.assertEqual([fact["member_name"] for fact in calls], ["Run", "Fake", "Hidden"])
        self.assertFalse(any(fact.get("action_name") == "Interpolated" for fact in graph["facts"]))
        self.assertTrue(any(item["kind"] == "route_action" and "interpolated" in item["reason"] for item in graph["unresolved"]))
        self.assertTrue(any(item["kind"] == "receiver_invocation_syntax" and "shadow" in item["reason"] for item in graph["unresolved"]))
        self.assertFalse(any(link["kind"] == "invocation_uses_injection" for link in graph["links"]))
        injection = next(fact for fact in graph["facts"] if fact["kind"] == "constructor_injection" and fact["owner_type_id"].endswith("FeedController`0"))
        self.assertNotIn("resolved_type_id", injection)
        candidate = next(item for item in graph["candidates"] if item["subject_fact_id"] == injection["id"])
        self.assertFalse(candidate["traversable"])
        self.assertTrue(candidate["candidate_fact_ids"])
        self.assertTrue(any(item["kind"] == "type_binding_candidate" and item["fact_id"] == injection["id"] for item in graph["unresolved"]))
        self.assertEqual(graph["extractor_identity"], "csharp-lexical-facts-v8:python-stdlib-lexer")
        self.assertTrue(graph["limitations"])

    def test_expression_body_method_spans_include_semicolon_and_preserve_overloads(self):
        shapes = self.repo / "SpanShapes.cs"
        shapes.write_text('''class SpanShapes
{
    bool Plain() => true;
    bool Spaced() => true    ;
    bool Commented() => true /* gap */;
    int Convert(int value) => value;
    string Convert(string value) => value;
    void Block() { }
}
''', encoding="utf-8")
        captured = self.repo / "ToBoolCaptured.cs"
        prefix = "class ToBoolCaptured {\n"
        captured_method = "private static bool ToBool(byte value) => value != 0;"
        self.assertLessEqual(len(prefix), 8062)
        captured.write_text(prefix + (" " * (8062 - len(prefix))) + captured_method + "\n}\n", encoding="utf-8")
        git(self.repo, "add", "--", "SpanShapes.cs", "ToBoolCaptured.cs")

        indexed = self.index()
        facts = self.graph(indexed["snapshot_id"])["facts"]
        methods = [fact for fact in facts if fact.get("kind") == "method_declaration"]
        by_name = {name: next(fact for fact in methods if fact.get("method_name") == name and fact["source"]["path"] == "SpanShapes.cs")
                   for name in ("Plain", "Spaced", "Commented", "Block")}
        source = shapes.read_text(encoding="utf-8")
        for name, expected in {
            "Plain": "bool Plain() => true;",
            "Spaced": "bool Spaced() => true    ;",
            "Commented": "bool Commented() => true /* gap */;",
        }.items():
            span = by_name[name]["source"]["span"]
            self.assertEqual(source[span["start_offset"]:span["end_offset"]], expected)
        block_span = by_name["Block"]["source"]["span"]
        self.assertEqual(source[block_span["start_offset"]:block_span["end_offset"]], "void Block() { }")

        overloads = [fact for fact in methods if fact.get("method_name") == "Convert" and fact["source"]["path"] == "SpanShapes.cs"]
        self.assertEqual(len(overloads), 2)
        self.assertEqual(len({(fact["id"], fact["source"]["span"]["start_offset"], fact["source"]["span"]["end_offset"])
                              for fact in overloads}), 2)
        captured_fact = next(fact for fact in methods if fact.get("method_name") == "ToBool"
                             and fact["source"]["path"] == "ToBoolCaptured.cs")
        self.assertEqual((captured_fact["source"]["span"]["start_offset"], captured_fact["source"]["span"]["end_offset"]),
                         (8062, 8115))

    def test_ambiguous_namespace_type_identity_is_not_joined(self):
        source = self.repo / "Ambiguous.cs"
        source.write_text('''namespace Left { class Service {} }\nnamespace Right { class Service {} }\nnamespace Consumer { class Owner(Service service) {} }\n''', encoding="utf-8")
        git(self.repo, "add", "--", "Ambiguous.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        owner = next(fact for fact in graph["facts"] if fact["kind"] == "constructor_injection" and fact["owner_type_id"] == "Consumer.Owner`0")
        self.assertNotIn("resolved_type_id", owner)
        candidates = next(item for item in graph["candidates"] if item["subject_fact_id"] == owner["id"])
        self.assertFalse(candidates["traversable"])

    def test_alias_interpolated_string_foreach_shadow_and_absolute_route_stay_unlinked(self):
        source = self.repo / "BoundaryCases.cs"
        source.write_text(r'''using Implementation = External.Implementation;
namespace Local { class Implementation {} }
namespace Demo;
interface IService {}
class Owner(IService service)
{
    [Route("api/demo")]
    class NestedController
    {
        [HttpGet("/absolute")]
        void Absolute() {}
    }
    void Run(System.Collections.Generic.IEnumerable<IService> others)
    {
        foreach (var service in others) { service.Ping(); }
        var text = $"{ "services.AddScoped<IService, Implementation>()" }";
    }
}
class Setup { void Configure() { services.AddScoped<IService, Implementation>(); } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "BoundaryCases.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        facts = graph["facts"]

        registration = next(f for f in facts if f["kind"] == "dependency_registration")
        self.assertNotIn("implementation_type_id", registration)
        self.assertFalse(any(link["kind"] == "registration_implements_type" and link["from_fact_id"] == registration["id"] for link in graph["links"]))
        self.assertTrue(any(item.get("fact_id") == registration["id"] and "alias" in item["reason"] for item in graph["unresolved"]))

        self.assertEqual(len([f for f in facts if f["kind"] == "dependency_registration"]), 1)
        self.assertTrue(any(f["kind"] == "receiver_invocation_syntax" and f["member_name"] == "Ping" for f in facts))
        self.assertTrue(any(item["kind"] == "receiver_invocation_syntax" and "shadow" in item["reason"] for item in graph["unresolved"]))

        absolute = next(f for f in facts if f["kind"] == "route_action" and f["action_name"] == "Absolute")
        self.assertEqual(absolute["route_literal"], "absolute")
        self.assertIsNone(absolute["controller_route_literal"])
        self.assertFalse(any("type_id" in fact and fact["kind"] in {"constructor_injection", "dependency_registration"} for fact in facts))
        self.assertFalse(any(link["kind"] in {"registration_implements_type", "injection_resolved_by_registration"} for link in graph["links"]))

    def test_typed_lambda_receiver_spelling_is_nontraversable_candidate(self):
        source = self.repo / "LambdaReceiver.cs"
        source.write_text('''namespace Demo;
interface IService {}
class Owner(IService service)
{
    void Run() { values.Select((IService service) => service.Ping()); }
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "LambdaReceiver.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        injection = next(f for f in graph["facts"] if f["kind"] == "constructor_injection" and f["parameter_name"] == "service")
        invocation = next(f for f in graph["facts"] if f["kind"] == "receiver_invocation_syntax" and f["member_name"] == "Ping")
        self.assertNotIn("injection_fact_id", invocation)
        self.assertFalse(any(link["kind"] == "invocation_uses_injection" for link in graph["links"]))
        candidate = next(c for c in graph["candidates"] if c["subject_fact_id"] == invocation["id"])
        self.assertFalse(candidate["traversable"])
        self.assertIn(injection["id"], candidate["candidate_fact_ids"])
        self.assertTrue(any(u["kind"] == "receiver_invocation_syntax" and u["fact_id"] == invocation["id"] for u in graph["unresolved"]))

    def test_using_alias_on_constructor_injection_does_not_resolve_to_local_same_name(self):
        source = self.repo / "InjectionAlias.cs"
        source.write_text('''using Service = External.Service;
namespace Local { class Service {} }
namespace Demo { class Owner(Service service) { void Run() { service.Ping(); } } class Setup { void Configure() { services.AddScoped<Local.Service, Local.Service>(); } } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "InjectionAlias.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        injection = next(f for f in graph["facts"] if f["kind"] == "constructor_injection" and f["owner_type_id"] == "Demo.Owner`0")
        self.assertNotIn("resolved_type_id", injection)
        self.assertTrue(any(item["subject_fact_id"] == injection["id"] for item in graph["candidates"]))
        self.assertFalse(any(link["kind"] == "injection_resolved_by_registration" and link["from_fact_id"] == injection["id"] for link in graph["links"]))

    def test_unimported_namespace_type_is_only_a_nontraversable_candidate(self):
        source = self.repo / "NamespaceScope.cs"
        source.write_text('''using Imported;
using External;
namespace Local { class Service {} }
namespace Imported { class ImportedService {} }
namespace Consumer { class InScope {} class Owner(Service missing, InScope local, ImportedService imported) {} class Setup { void Configure() { services.AddScoped<InScope, InScope>(); services.AddScoped<ImportedService, ImportedService>(); } } }
''', encoding="utf-8")
        git(self.repo, "add", "--", "NamespaceScope.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        injections = {f["parameter_name"]: f for f in graph["facts"] if f["kind"] == "constructor_injection" and f["owner_type_id"] == "Consumer.Owner`0"}
        self.assertNotIn("resolved_type_id", injections["missing"])
        self.assertTrue({item["subject_fact_id"] for item in graph["candidates"]} >= {fact["id"] for fact in injections.values()})
        self.assertTrue(all(item["traversable"] is False for item in graph["candidates"]))
        self.assertFalse(any(link["kind"] == "injection_resolved_by_registration" and link["from_fact_id"] == injections["missing"]["id"] for link in graph["links"]))

    def test_multiline_raw_route_literal_is_unresolved(self):
        source = self.repo / "RawRoute.cs"
        source.write_text('''namespace Demo;
[Route("""
    api/demo
    """)]
class Controller { [HttpGet] void Get() {} }
''', encoding="utf-8")
        git(self.repo, "add", "--", "RawRoute.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        self.assertFalse(any(f["kind"] == "route_action" and f["source"]["path"] == "RawRoute.cs" for f in graph["facts"]))
        self.assertTrue(any(item["kind"] == "controller_route" and "multiline raw" in item["reason"] for item in graph["unresolved"]))
        self.assertTrue(any(item["kind"] == "route_action" and "suppressed" in item["reason"] for item in graph["unresolved"]))

    def test_reviewed_flow_overlay_round_trip_and_rejects_stale_or_mismatched_evidence(self):
        source = self.repo / "Overlay.cs"
        source.write_text('''namespace Demo; [Route("api/demo")] class Controller { [HttpGet("items")] void Get() {} }
''', encoding="utf-8")
        git(self.repo, "add", "--", "Overlay.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        route = next(fact for fact in graph["facts"] if fact["kind"] == "route_action")
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Reviewed demo browsing flow",
            "reviewed_conclusions": [{
                "claim": "The cited action serves the route recorded in this reviewed flow.",
                "evidence": [{"fact_id": route["id"], "source": route["source"]}],
            }],
        }
        overlay_path = self.root / "flow.json"

        def write_overlay(value):
            overlay_path.write_text(json.dumps(value), encoding="utf-8")

        write_overlay(overlay)
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path)).stdout)
        overlay_id = attached["overlay_id"]
        reopened = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id).stdout)
        self.assertEqual(reopened["overlay"]["title"], overlay["title"])
        self.assertEqual(reopened["overlay"]["content_hash"], overlay_id)
        self.assertEqual(reopened["review_status"], "unreviewed")
        self.assertIn("not mechanically validated", reopened["validation"])
        self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", "10000", expect=2)

        receipt = {
            "receipt_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "overlay_id": overlay_id,
            "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"],
            "reviewer_identity": "independent review",
            "reviewer_model": "GPT-6.1 Sol High",
            "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z",
            "review_basis": "All five reviewed conclusions are supported by the cited spans; the distributed cache wording does not claim durable shared storage.",
        }
        receipt_path = self.root / "review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_result = json.loads(self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--input", os.fspath(receipt_path)).stdout)
        accepted = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id).stdout)
        self.assertEqual(accepted["review_status"], "accepted")
        self.assertEqual(accepted["review_receipt"]["receipt_hash"], receipt_result["receipt_hash"])
        large = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", "5000")
        large_json = json.loads(large.stdout)
        snippet_by_id = {item["snippet_id"]: item for item in large_json["source_snippets"]}
        anchor_by_id = {item["source_id"]: item for item in large_json["source_anchors"]}
        self.assertTrue(all(set(item) == {"snippet_id", "source_id", "span", "text"} for item in large_json["source_snippets"]))
        self.assertEqual(len(snippet_by_id), len(large_json["source_snippets"]))
        self.assertTrue(all(snippet["source_id"] in anchor_by_id for snippet in large_json["source_snippets"]))
        referenced_snippets = {item["snippet_id"] for claim in large_json["claims"] for item in claim["evidence"]}
        referenced_sources = {item["source_id"] for claim in large_json["claims"] for item in claim["evidence"]}
        self.assertEqual(referenced_snippets, set(snippet_by_id))
        self.assertEqual(referenced_sources, set(anchor_by_id))
        self.assertTrue(all(item["snippet_id"] in snippet_by_id for claim in large_json["claims"] for item in claim["evidence"]))
        exact_size = large_json["budget"]["stdout_bytes_including_newline"]
        self.assertEqual(len(large.stdout.encode("ascii")), exact_size)
        exact = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", str(exact_size))
        self.assertEqual(len(exact.stdout.encode("ascii")), exact_size)
        one_short = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", str(exact_size - 1))
        short_json = json.loads(one_short.stdout)
        self.assertLessEqual(len(one_short.stdout.encode("ascii")), exact_size - 1)
        self.assertEqual(short_json["claim_selection"]["omitted_claims"], 1)
        repeated_short = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--max-tokens", str(exact_size - 1))
        repeated_json = json.loads(repeated_short.stdout)
        self.assertEqual(repeated_json["claims"], short_json["claims"])
        self.assertEqual(repeated_json["claim_selection"], short_json["claim_selection"])
        short_snippets = {item["snippet_id"] for item in short_json["source_snippets"]}
        self.assertTrue(short_snippets.issubset(snippet_by_id))
        self.assertEqual(
            {item["snippet_id"] for claim in short_json["claims"] for item in claim["evidence"]},
            short_snippets,
        )
        replaced_receipt = dict(receipt, decision="rejected", review_basis="Attempted conflicting receipt.")
        receipt_path.write_text(json.dumps(replaced_receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id, "--input", os.fspath(receipt_path), expect=2)
        still_accepted = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", overlay_id).stdout)
        self.assertEqual(still_accepted["review_status"], "accepted")

        stale = dict(overlay, snapshot_id="atlas-v2-stale")
        write_overlay(stale)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)
        unknown_fact = json.loads(json.dumps(overlay))
        unknown_fact["reviewed_conclusions"][0]["evidence"][0]["fact_id"] = "missing-fact"
        write_overlay(unknown_fact)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)
        wrong_extractor = dict(overlay, extractor_identity="different-extractor")
        write_overlay(wrong_extractor)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)
        wrong_source = json.loads(json.dumps(overlay))
        wrong_source["reviewed_conclusions"][0]["evidence"][0]["source"]["sha256"] = "0" * 64
        write_overlay(wrong_source)
        self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path), expect=2)

        changed_claim = json.loads(json.dumps(overlay))
        changed_claim["reviewed_conclusions"][0]["claim"] += " Revised wording."
        write_overlay(changed_claim)
        changed = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path)).stdout)
        changed_status = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"]).stdout)
        self.assertNotEqual(changed["overlay_id"], overlay_id)
        self.assertEqual(changed_status["review_status"], "unreviewed")

        mismatch = dict(receipt, overlay_id=changed["overlay_id"])
        receipt_path.write_text(json.dumps(mismatch), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"], "--input", os.fspath(receipt_path), expect=2)
        rejected = dict(receipt, overlay_id=changed["overlay_id"], overlay_content_hash=changed["content_hash"], decision="rejected", review_basis="Changed claim wording has not received semantic review.")
        receipt_path.write_text(json.dumps(rejected), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"], "--input", os.fspath(receipt_path))
        rejected_status = json.loads(self.cli("flow-query", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"]).stdout)
        self.assertEqual(rejected_status["review_status"], "rejected")
        self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", changed["overlay_id"], "--max-tokens", "10000", expect=2)

    def test_focus_refuses_same_status_different_bytes_and_missing_source(self):
        source = self.repo / "Tracked.cs"
        source.write_text("namespace Demo; class Widget {}\n", encoding="utf-8")
        git(self.repo, "add", "--", "Tracked.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        fact = next(f for f in graph["facts"] if f["kind"] == "type_declaration" and f["source"]["path"] == "Tracked.cs")
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Fixture reviewed flow",
            "reviewed_conclusions": [{"claim": "The fixture declares Widget.", "evidence": [{"fact_id": fact["id"], "source": fact["source"]}]}],
        }
        overlay_path = self.root / "focus-flow.json"
        overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_path)).stdout)
        receipt = {
            "receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"], "reviewer_identity": "reviewer",
            "reviewer_model": "test model", "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "Fixture evidence reviewed.",
        }
        receipt_path = self.root / "focus-review.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_path))

        source.write_text("namespace Demo; class Widget { int Value => 1; }\n", encoding="utf-8")
        first = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--max-tokens", "10000", expect=3)
        first_json = json.loads(first.stdout)
        first_status = first_json["freshness"]["structured_status"]
        first_head = first_json["freshness"]["head"]
        self.assertEqual(first_json["result"], "stale_refused")
        self.assertEqual(first_json["claims"], [])
        self.assertEqual(first_json["freshness"]["changed_paths"], ["Tracked.cs"])
        stale_size = len(first.stdout.encode("ascii"))
        self.assertEqual(first_json["budget"]["stdout_bytes_including_newline"], stale_size)
        exact_stale = self.cli(
            "focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"],
            "--max-tokens", str(stale_size), expect=3,
        )
        self.assertEqual(len(exact_stale.stdout.encode("ascii")), stale_size)
        short_stale = self.cli(
            "focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
            "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"],
            "--max-tokens", str(stale_size - 1), expect=2,
        )
        self.assertEqual(short_stale.stdout, "")
        self.assertIn(f"requires {stale_size} ASCII stdout bytes", short_stale.stderr)
        self.assertIn("diagnostic and claims withheld", short_stale.stderr)

        source.write_text("namespace Demo; class Widget { string? Name; }\n", encoding="utf-8")
        second = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--max-tokens", "10000", expect=3)
        second_json = json.loads(second.stdout)
        self.assertEqual(second_json["freshness"]["head"], first_head)
        self.assertEqual(second_json["freshness"]["structured_status"], first_status)
        self.assertEqual(second_json["freshness"]["changed_paths"], ["Tracked.cs"])
        self.assertTrue(any("content hash changed" in reason for reason in second_json["freshness"]["reasons"]))

        source.unlink()
        missing = self.cli("focus", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--max-tokens", "10000", expect=3)
        missing_json = json.loads(missing.stdout)
        self.assertEqual(missing_json["claims"], [])
        self.assertEqual(missing_json["freshness"]["changed_paths"], ["Tracked.cs"])

    def test_answer_check_binds_complete_fresh_packet_and_preserves_exact_accepted_draft(self):
        source = self.repo / "Answer.cs"
        source.write_text('''namespace Demo;
class Widget
{
    private readonly int _id;
    Widget(int id) { _id = id; }
    object Create(int id) => Build(new Widget(id), mode: Mode.Exact);
    object Build(Widget value, Mode mode) => new Result(false, 0, value, mode);
    bool Success;
    int MatchedCount;
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Answer.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        create_fact = next(item for item in graph["facts"] if item.get("method_name") == "Create" and item["source"]["path"] == "Answer.cs")
        build_fact = next(item for item in graph["facts"] if item.get("method_name") == "Build" and item["source"]["path"] == "Answer.cs")
        fact = create_fact
        overlay = {
            "overlay_schema_version": 1,
            "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"],
            "title": "Answer fixture map",
            "reviewed_conclusions": [
                {"claim": "The response has success = false and matched_count = 0.", "evidence": [
                    {"fact_id": fact["id"], "source": fact["source"]},
                    {"fact_id": build_fact["id"], "source": build_fact["source"]},
                ]},
                {"claim": "The controller is declared as a C# class.", "evidence": [{"fact_id": fact["id"], "source": fact["source"]}]},
            ],
        }
        overlay_file = self.root / "answer-flow.json"
        overlay_file.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_file)).stdout)
        review_receipt = {
            "receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"],
            "extractor_identity": graph["extractor_identity"], "reviewer_identity": "independent reviewer",
            "reviewer_model": "GPT-6.1 Sol High", "decision": "accepted",
            "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "The source spans support both map claims.",
        }
        receipt_file = self.root / "answer-flow-review.json"
        receipt_file.write_text(json.dumps(review_receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_file))
        question_file = self.root / "question.txt"
        draft_file = self.root / "draft.txt"
        question_file.write_bytes("What does selfie upload return?\n".encode())
        draft_bytes = "It returns success=false, matched_count=0, history, and no new rows.\n".encode()
        draft_file.write_bytes(draft_bytes)

        args = ("answer-check", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--question-file", os.fspath(question_file), "--draft-file", os.fspath(draft_file))
        prepared = self.cli(*args)
        packet = json.loads(prepared.stdout)
        self.assertEqual(packet["result"], "semantic_review_required")
        self.assertEqual(packet["question"], question_file.read_text())
        self.assertEqual(packet["draft"], draft_file.read_text())
        self.assertEqual([claim["claim_number"] for claim in packet["claims"]], [1, 2])
        self.assertEqual(packet["binding"]["overlay_content_hash"], attached["content_hash"])
        self.assertEqual(packet["binding"]["question_sha256"], hashlib.sha256(question_file.read_bytes()).hexdigest())
        cited_text = "\n".join(item["text"] for item in packet["source_snippets"])
        self.assertIn("object Create(int id) => Build(new Widget(id), mode: Mode.Exact)", cited_text)
        self.assertIn("object Build(Widget value, Mode mode) => new Result(false, 0, value, mode)", cited_text)
        self.assertIn("may be accepted even when the map claim paraphrase omits them", packet["review_instructions"])
        self.assertIn("complete relevant coverage", packet["review_instructions"])
        self.assertIn("contradictions", packet["review_instructions"])
        self.assertIn("candidate bindings", packet["review_instructions"])
        self.assertTrue(all("snippet_id" in item for claim in packet["claims"] for item in claim["evidence"]))
        packet_hash = hashlib.sha256(prepared.stdout.encode("ascii")).hexdigest()

        review_file = self.root / "answer-review.json"
        review = {
            "packet_sha256": packet_hash,
            "decision": "accepted",
            "reviewer_identity": "sol-high-review-session",
            "reviewer_model": "GPT-6.1 Sol High",
            "claim_reviews": [
                {"claim_number": 1, "disposition": "covered", "basis": "Both response fields are relevant to the question and appear with their exact values."},
                {"claim_number": 2, "disposition": "not_relevant", "basis": "The C# declaration form does not answer what the upload operation returns."},
            ],
        }
        review_file.write_text(json.dumps(review), encoding="utf-8")
        accepted = self.cli(*args, "--review", os.fspath(review_file))
        self.assertEqual(accepted.stdout.encode(), draft_bytes)

        question_file.write_text("What exact value does selfie upload return?\n", encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        question_file.write_bytes(b"What does selfie upload return?\n")

        bare = json.loads(json.dumps(review))
        bare["claim_reviews"][0]["basis"] = "used"
        review_file.write_text(json.dumps(bare), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        invalid_disposition = json.loads(json.dumps(review))
        invalid_disposition["claim_reviews"][0]["disposition"] = "supported"
        review_file.write_text(json.dumps(invalid_disposition), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        duplicate_claim = json.loads(json.dumps(review))
        duplicate_claim["claim_reviews"][1]["claim_number"] = 1
        review_file.write_text(json.dumps(duplicate_claim), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        missing_identity = json.loads(json.dumps(review))
        del missing_identity["reviewer_model"]
        review_file.write_text(json.dumps(missing_identity), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)
        changed = dict(review, packet_sha256="0" * 64)
        review_file.write_text(json.dumps(changed), encoding="utf-8")
        self.cli(*args, "--review", os.fspath(review_file), expect=2)

    def test_focus_exact_snippet_identity_unicode_and_fail_closed_source_checks(self):
        source = self.repo / "Exact.cs"
        raw = "\ufeffΩ\r\nreturn x;\r\nreturn x;\n".encode("utf-8")
        source.write_bytes(raw)
        decoded = raw.decode("utf-8-sig")
        first_start = decoded.index("return x;")
        second_start = decoded.index("return x;", first_start + 1)

        def citation(fact_id, start):
            end = start + len("return x;")
            return {
                "fact_id": fact_id,
                "source": {
                    "path": "Exact.cs",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "span": {"offset_unit": "unicode_codepoint", "start_offset": start, "end_offset": end},
                },
            }

        first, repeated, other_span = citation("fact-a", first_start), citation("fact-b", first_start), citation("fact-c", second_start)
        claims = [
            {"claim": "first", "evidence": [first]},
            {"claim": "same span, another fact", "evidence": [repeated]},
            {"claim": "same text, another span", "evidence": [other_span]},
        ]
        verified = ATLAS._source_texts(self.repo, [(item["fact_id"], item["source"]) for claim in claims for item in claim["evidence"]])
        common = {
            "snapshot_id": "snapshot",
            "extractor_identity": "extractor",
            "review_status": "accepted",
            "reviewer": {"identity": "reviewer", "model": "model", "decision": "accepted", "reviewed_at": "now"},
        }
        flow = {"overlay": {"reviewed_conclusions": claims, "extractor_identity": "extractor"}, "overlay_id": "overlay", "review_status": "accepted", "review_receipt": {"reviewer_identity": "reviewer", "reviewer_model": "model", "decision": "accepted", "reviewed_at": "now"}}
        freshness = {"repository_root": os.fspath(self.repo)}
        document, encoded = ATLAS._focus_document(common, flow, freshness, 100000, verified)
        self.assertEqual(document["budget"]["stdout_bytes_including_newline"], len(encoded))
        self.assertEqual([item["text"] for item in document["source_snippets"]], ["return x;", "return x;"])
        self.assertNotEqual(document["source_snippets"][0]["snippet_id"], document["source_snippets"][1]["snippet_id"])
        self.assertEqual(document["claims"][0]["evidence"][0]["snippet_id"], document["claims"][1]["evidence"][0]["snippet_id"])
        self.assertNotEqual(document["claims"][0]["evidence"][0]["snippet_id"], document["claims"][2]["evidence"][0]["snippet_id"])
        self.assertEqual([item["fact_id"] for claim in document["claims"] for item in claim["evidence"]], ["fact-a", "fact-b", "fact-c"])
        reordered, _ = ATLAS._focus_document(common, {**flow, "overlay": {**flow["overlay"], "reviewed_conclusions": [claims[2], claims[0]]}}, freshness, 100000, verified)
        original_ids = {item["text"] + str(item["span"]["start_offset"]): item["snippet_id"] for item in document["source_snippets"]}
        reordered_ids = {item["text"] + str(item["span"]["start_offset"]): item["snippet_id"] for item in reordered["source_snippets"]}
        self.assertEqual(reordered_ids, original_ids)
        self.assertEqual(decoded[first_start:first_start + len("return x;")], "return x;")

        wrong_hash = dict(first["source"], sha256="0" * 64)
        with self.assertRaisesRegex(ATLAS.AtlasError, "source hash changed"):
            ATLAS._source_texts(self.repo, [("fact-a", wrong_hash)])
        outside = self.root / "outside.cs"
        outside.write_bytes(raw)
        (self.repo / "unsafe.cs").symlink_to(outside)
        unsafe = {"path": "unsafe.cs", "sha256": hashlib.sha256(raw).hexdigest(), "span": first["source"]["span"]}
        with self.assertRaisesRegex(ATLAS.AtlasError, "missing or not a regular file"):
            ATLAS._source_texts(self.repo, [("unsafe-fact", unsafe)])

    def test_answer_check_refuses_unaccepted_or_stale_focus(self):
        source = self.repo / "Answer.cs"
        source.write_text("namespace Demo; class Widget {}\n", encoding="utf-8")
        git(self.repo, "add", "--", "Answer.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        fact = next(item for item in graph["facts"] if item["kind"] == "type_declaration" and item["source"]["path"] == "Answer.cs")
        overlay = {"overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"], "extractor_identity": graph["extractor_identity"], "title": "Map", "reviewed_conclusions": [{"claim": "Widget exists.", "evidence": [{"fact_id": fact["id"], "source": fact["source"]}]}]}
        overlay_file = self.root / "unaccepted-flow.json"
        overlay_file.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_file)).stdout)
        question_file, draft_file = self.root / "q.txt", self.root / "d.txt"
        question_file.write_text("What exists?")
        draft_file.write_text("Widget exists.")
        args = ("answer-check", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--question-file", os.fspath(question_file), "--draft-file", os.fspath(draft_file))
        self.cli(*args, expect=2)

        receipt = {"receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"], "overlay_id": attached["overlay_id"], "overlay_content_hash": attached["content_hash"], "extractor_identity": graph["extractor_identity"], "reviewer_identity": "reviewer", "reviewer_model": "test", "decision": "accepted", "reviewed_at": "2026-10-06T12:00:00Z", "review_basis": "Widget claim checked against source."}
        receipt_file = self.root / "review.json"
        receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_file))
        source.write_text("namespace Demo; class Widget { int Value; }\n", encoding="utf-8")
        self.cli(*args, expect=2)

    def test_answer_check_refuses_incomplete_focus(self):
        spec = importlib.util.spec_from_file_location("atlas_answer_check_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        incomplete = {"result": "fresh", "claim_selection": {"included_claims": 1, "total_claims": 2, "omitted_claims": 1}, "claims": []}
        with mock.patch.object(module, "focus", return_value=(incomplete, b"{}\n", 0)):
            with self.assertRaisesRegex(module.AtlasError, "requires every reviewed claim"):
                module.answer_check("unused", "unused", "snapshot", "overlay", "unused", "unused", None)

    def test_answer_lifecycle_one_rejection_correction_acceptance_and_guards(self):
        source = self.repo / "Answer.cs"
        source.write_text('''namespace Demo;
class Widget
{
    object Create(int id) => Build(new Widget(id), mode: Mode.Exact);
    object Build(Widget value, Mode mode) => new Result(false, 0, value, mode);
}
''', encoding="utf-8")
        git(self.repo, "add", "--", "Answer.cs")
        saved = self.index()
        graph = self.graph(saved["snapshot_id"])
        create_fact = next(item for item in graph["facts"] if item.get("method_name") == "Create" and item["source"]["path"] == "Answer.cs")
        build_fact = next(item for item in graph["facts"] if item.get("method_name") == "Build" and item["source"]["path"] == "Answer.cs")
        overlay = {
            "overlay_schema_version": 1, "snapshot_id": saved["snapshot_id"],
            "extractor_identity": graph["extractor_identity"], "title": "Answer lifecycle map",
            "reviewed_conclusions": [
                {"claim": "The returned result has success=false and matched_count=0.", "evidence": [
                    {"fact_id": create_fact["id"], "source": create_fact["source"]},
                    {"fact_id": build_fact["id"], "source": build_fact["source"]},
                ]},
                {"claim": "Widget is a C# class.", "evidence": [{"fact_id": create_fact["id"], "source": create_fact["source"]}]},
            ],
        }
        overlay_file = self.root / "lifecycle-flow.json"
        overlay_file.write_text(json.dumps(overlay), encoding="utf-8")
        attached = json.loads(self.cli("flow-add", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--input", os.fspath(overlay_file)).stdout)
        receipt = {
            "receipt_schema_version": 1, "snapshot_id": saved["snapshot_id"], "overlay_id": attached["overlay_id"],
            "overlay_content_hash": attached["content_hash"], "extractor_identity": graph["extractor_identity"],
            "reviewer_identity": "independent flow reviewer", "reviewer_model": "GPT-6.1 Sol High",
            "decision": "accepted", "reviewed_at": "2026-10-06T12:00:00Z",
            "review_basis": "Both claims are grounded in the exact saved method spans.",
        }
        receipt_file = self.root / "lifecycle-flow-review.json"
        receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
        self.cli("flow-review", "--db", os.fspath(self.db), "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"], "--input", os.fspath(receipt_file))

        question_file = self.root / "lifecycle-question.txt"
        draft_file = self.root / "lifecycle-draft.txt"
        question_file.write_text("What exact result values does the operation return?\n", encoding="utf-8")
        draft_file.write_text("It returns success=false.\n", encoding="utf-8")
        base = ("answer-lifecycle", "prepare", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                "--snapshot", saved["snapshot_id"], "--overlay", attached["overlay_id"],
                "--question-file", os.fspath(question_file), "--draft-file", os.fspath(draft_file))
        initial_result = self.cli(*base)
        initial_bytes = initial_result.stdout
        initial = json.loads(initial_bytes)
        self.assertEqual(initial["result"], "semantic_review_required")
        self.assertEqual(initial_bytes, self.cli(*base).stdout)
        contract = initial["review_contract"]
        self.assertEqual(contract["required_top_level_fields"], [
            "review_schema_version", "packet_sha256", "decision", "reviewer_identity", "reviewer_model", "claim_reviews",
        ])
        self.assertEqual(contract["optional_top_level_fields"], ["rejection_reasons"])
        self.assertEqual(contract["claim_reviews"]["required_item_fields"], ["claim_number", "disposition", "basis"])
        self.assertEqual(contract["claim_reviews"]["allowed_dispositions"], ["covered", "not_relevant", "incomplete"])
        reason_shapes = contract["rejection_reasons"]["allowed_item_shapes"]
        self.assertEqual(reason_shapes[0]["required_fields"], ["scope", "claim_number", "reason", "correction"])
        self.assertEqual(reason_shapes[1]["required_fields"], ["scope", "category", "reason", "correction"])
        self.assertEqual(reason_shapes[1]["allowed_categories"], ["unsupported_addition", "contradiction"])
        self.assertEqual(contract["packet_hash_binding"]["value"], "copy packet.packet_sha256 exactly")
        self.assertEqual(contract["reviewer_fields"]["reviewer_identity"], "nonempty audit label")
        self.assertNotEqual(hashlib.sha256(initial_bytes.encode("ascii")).hexdigest(), initial["packet_sha256"])

        rejected_review = {
            "review_schema_version": 1, "packet_sha256": initial["packet_sha256"], "decision": "rejected",
            "reviewer_identity": "independent answer reviewer", "reviewer_model": "GPT-6.1 Sol High",
            "claim_reviews": [
                {"claim_number": 1, "disposition": "incomplete", "basis": "The cited Build span also returns matched_count=0, which the draft omits."},
                {"claim_number": 2, "disposition": "not_relevant", "basis": "The class declaration does not answer the requested result values."},
            ],
            "rejection_reasons": [
                {"scope": "claim", "claim_number": 1, "reason": "The draft omits the second returned result value.", "correction": "Add matched_count=0 as a separate supported assertion."},
            ],
        }
        rejected_file = self.root / "lifecycle-rejected-review.json"
        rejected_file.write_text(json.dumps(rejected_review), encoding="utf-8")
        rejected_call = self.cli(*base, "--review-file", os.fspath(rejected_file))
        correction = json.loads(rejected_call.stdout)
        self.assertEqual(correction["result"], "correction_required")
        self.assertEqual(correction["correction_round"], 1)
        self.assertEqual(correction["max_corrections"], 1)
        self.assertEqual(correction["rejected_claim_numbers"], [1])
        self.assertEqual(correction["claims"], initial["answer_packet"]["claims"])

        packet_claim = correction["claims"][0]
        answer_packet = correction["original_packet"]["answer_packet"]
        snippets = {item["snippet_id"]: item for item in answer_packet["source_snippets"]}
        evidence = next(item for item in packet_claim["evidence"] if "new Result(false, 0" in snippets[item["snippet_id"]]["text"])
        anchor = next(item for item in answer_packet["source_anchors"] if item["source_id"] == evidence["source_id"])
        citation = {
            "claim_number": 1, "fact_id": evidence["fact_id"], "path": anchor["path"],
            "sha256": anchor["sha256"], "span": evidence["span"], "snippet_id": evidence["snippet_id"],
        }
        corrected_draft = self.root / "lifecycle-corrected.txt"
        corrected_draft.write_text("It returns success=false. It also returns matched_count=0.\n", encoding="utf-8")
        answer_obj = {
            "question_id": "answer-values", "answer": corrected_draft.read_text(encoding="utf-8"),
            "material_claims": [
                {"assertion": "The result has success=false.", "claim_numbers": [1], "citations": [citation]},
                {"assertion": "The result has matched_count=0.", "claim_numbers": [1], "citations": [citation]},
            ],
            "limitations": ["This source packet establishes syntax-level source behavior only."],
            "evidence_measurement": {},
        }
        answer_file = self.root / "lifecycle-corrected-answer.json"
        answer_file.write_text(json.dumps(answer_obj), encoding="utf-8")
        correction_file = self.root / "lifecycle-correction-packet.json"
        correction_file.write_text(rejected_call.stdout, encoding="utf-8")
        correct_args = ("answer-lifecycle", "correct", "--correction-packet", os.fspath(correction_file),
                        "--draft-file", os.fspath(corrected_draft), "--answer-file", os.fspath(answer_file))
        corrected_call = self.cli(*correct_args)
        corrected_packet = json.loads(corrected_call.stdout)
        self.assertEqual(corrected_packet["result"], "semantic_review_required")
        self.assertEqual(corrected_call.stdout, self.cli(*correct_args).stdout)
        self.assertTrue(corrected_packet["review_contract"]["corrected_answer_review"])
        self.assertEqual(corrected_packet["review_contract"]["required_top_level_fields"], contract["required_top_level_fields"])

        # Characterize the old boundary with this real answer's clone: v1 preserves
        # worker-claimed byte and elapsed-time values without authenticating them.
        false_measurement = json.loads(json.dumps(answer_obj))
        false_measurement["evidence_measurement"] = {
            "canonical_evidence_bytes": 1, "elapsed_wall_seconds": 0.001,
            "stdout_bytes_including_newlines": 1,
        }
        answer_file.write_text(json.dumps(false_measurement), encoding="utf-8")
        v1_false_measurement = self.cli(*correct_args)
        self.assertEqual(json.loads(v1_false_measurement.stdout)["structured_answer"]["evidence_measurement"], false_measurement["evidence_measurement"])
        answer_file.write_text(json.dumps(answer_obj), encoding="utf-8")

        mismatch = dict(answer_obj, answer="different text")
        answer_file.write_text(json.dumps(mismatch), encoding="utf-8")
        self.assertEqual(self.cli(*correct_args, expect=2).stdout, "")
        answer_file.write_text(json.dumps(answer_obj), encoding="utf-8")
        bad_citation = json.loads(json.dumps(answer_obj))
        bad_citation["material_claims"][0]["citations"][0]["span"]["start_offset"] += 1
        answer_file.write_text(json.dumps(bad_citation), encoding="utf-8")
        self.assertEqual(self.cli(*correct_args, expect=2).stdout, "")
        answer_file.write_text(json.dumps(answer_obj), encoding="utf-8")

        malformed_reviews = []
        reordered = json.loads(json.dumps(rejected_review))
        reordered["claim_reviews"].reverse()
        malformed_reviews.append((reordered, "claim_reviews[0]"))
        bad_disposition_type = json.loads(json.dumps(rejected_review))
        bad_disposition_type["claim_reviews"][0]["disposition"] = []
        malformed_reviews.append((bad_disposition_type, "claim 1 disposition must be covered, not_relevant, or incomplete"))
        no_reason = json.loads(json.dumps(rejected_review))
        no_reason["rejection_reasons"] = []
        malformed_reviews.append((no_reason, "rejected review requires at least one structured rejection reason"))
        missing_claim_reason = json.loads(json.dumps(rejected_review))
        missing_claim_reason["rejection_reasons"] = [
            {"scope": "answer", "category": "contradiction", "reason": "A separate contradiction exists in the answer text.", "correction": "Remove the contradictory statement from the answer."},
        ]
        malformed_reviews.append((missing_claim_reason, "incomplete claim 1 requires a structured rejection reason"))
        bad_category_type = json.loads(json.dumps(rejected_review))
        bad_category_type["rejection_reasons"] = [
            {"scope": "answer", "category": {}, "reason": "A separate contradiction exists in the answer text.", "correction": "Remove the contradictory statement from the answer."},
        ]
        malformed_reviews.append((bad_category_type, "category must be unsupported_addition or contradiction"))
        bad_packet_hash = json.loads(json.dumps(rejected_review))
        bad_packet_hash["packet_sha256"] = "0" * 64
        malformed_reviews.append((bad_packet_hash, "packet_sha256 does not match"))
        accepted_incomplete = json.loads(json.dumps(rejected_review))
        accepted_incomplete["decision"] = "accepted"
        accepted_incomplete["rejection_reasons"] = []
        malformed_reviews.append((accepted_incomplete, "accepted review has incomplete claim 1"))
        for index, (invalid, expected_error) in enumerate(malformed_reviews):
            invalid_file = self.root / f"invalid-lifecycle-review-{index}.json"
            invalid_file.write_text(json.dumps(invalid), encoding="utf-8")
            rejected = self.cli(*base, "--review-file", os.fspath(invalid_file), expect=2)
            self.assertEqual(rejected.stdout, "")
            self.assertIn(expected_error, rejected.stderr)

        accepted_review = {
            "review_schema_version": 1, "packet_sha256": corrected_packet["packet_sha256"], "decision": "accepted",
            "reviewer_identity": "fresh independent answer reviewer", "reviewer_model": "GPT-6.1 Sol High",
            "claim_reviews": [
                {"claim_number": 1, "disposition": "covered", "basis": "The corrected assertions include both exact result values from the cited method body."},
                {"claim_number": 2, "disposition": "not_relevant", "basis": "The declaration shape is unrelated to the exact result values requested."},
            ],
        }
        accepted_file = self.root / "lifecycle-accepted-review.json"
        accepted_file.write_text(json.dumps(accepted_review), encoding="utf-8")
        accept_args = ("answer-lifecycle", "accept", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                       "--packet-file", os.fspath(self.root / "corrected-review-packet.json"),
                       "--review-file", os.fspath(accepted_file))
        corrected_packet_file = self.root / "corrected-review-packet.json"
        corrected_packet_file.write_text(corrected_call.stdout, encoding="utf-8")
        final = json.loads(self.cli(*accept_args).stdout)
        self.assertEqual(final["result"], "accepted")
        self.assertEqual(final["answer"], answer_obj)
        self.assertEqual(final["answer_sha256"], hashlib.sha256(answer_obj["answer"].encode("utf-8")).hexdigest())
        self.assertEqual(self.cli(*accept_args).stdout, self.cli(*accept_args).stdout)

        # Version 2 binds Atlas's exact evidence-content measurement to the
        # original packet and rechecks it after a fresh semantic review.
        v2_base = (*base, "--lifecycle-version", "2")
        v2_initial_call = self.cli(*v2_base)
        v2_initial = json.loads(v2_initial_call.stdout)
        self.assertEqual(v2_initial["lifecycle_schema_version"], 2)
        self.assertEqual(v2_initial_call.stdout, self.cli(*v2_base).stdout)
        self.assertEqual(v2_initial["review_contract"]["review_schema_version"], 1)
        self.assertEqual(v2_initial["measurement_contract"]["measurement_schema_version"], "integer, exactly 1")
        direct_review = {
            "review_schema_version": 1, "packet_sha256": v2_initial["packet_sha256"], "decision": "accepted",
            "reviewer_identity": "direct initial reviewer", "reviewer_model": "GPT-6.1 Sol High",
            "claim_reviews": [
                {"claim_number": claim["claim_number"], "disposition": "covered" if claim["claim_number"] == 1 else "not_relevant",
                 "basis": "The exact cited snippets were checked for this initial accepted answer review."}
                for claim in v2_initial["answer_packet"]["claims"]
            ],
        }
        direct_review_file = self.root / "v2-direct-review.json"
        direct_review_file.write_text(json.dumps(direct_review), encoding="utf-8")
        direct_accepted = json.loads(self.cli(*v2_base, "--review-file", os.fspath(direct_review_file)).stdout)
        direct_measurement = ATLAS._canonical_review_evidence_measurement(v2_initial)
        self.assertEqual(direct_accepted["evidence_measurement"], direct_measurement)
        self.assertEqual(direct_accepted["lifecycle_schema_version"], 2)
        # The v1 direct branch remains its original package shape; use a review
        # bound to the v1 packet for an exact semantic comparison.
        v1_direct_review = dict(direct_review, packet_sha256=initial["packet_sha256"])
        v1_direct_review_file = self.root / "v1-direct-review.json"
        v1_direct_review_file.write_text(json.dumps(v1_direct_review), encoding="utf-8")
        v1_direct_accepted = json.loads(self.cli(*base, "--review-file", os.fspath(v1_direct_review_file)).stdout)
        self.assertEqual(v1_direct_accepted["lifecycle_schema_version"], 1)
        self.assertNotIn("evidence_measurement", v1_direct_accepted)
        self.assertNotIn("measurement_contract", v1_direct_accepted)

        v2_rejected_review = dict(rejected_review, packet_sha256=v2_initial["packet_sha256"])
        v2_rejected_file = self.root / "v2-rejected-review.json"
        v2_rejected_file.write_text(json.dumps(v2_rejected_review), encoding="utf-8")
        v2_correction_stdout = self.cli(*v2_base, "--review-file", os.fspath(v2_rejected_file)).stdout
        v2_correction_file = self.root / "v2-correction-packet.json"
        v2_correction_file.write_text(v2_correction_stdout, encoding="utf-8")
        v2_correction = json.loads(v2_correction_stdout)
        self.assertEqual(v2_correction["lifecycle_schema_version"], 2)
        false_measurement_answer_file = self.root / "v2-false-measurement-answer.json"
        false_measurement_answer_file.write_text(json.dumps(false_measurement), encoding="utf-8")
        v2_correct_args = ("answer-lifecycle", "correct", "--correction-packet", os.fspath(v2_correction_file),
                           "--draft-file", os.fspath(corrected_draft), "--answer-file", os.fspath(false_measurement_answer_file))
        rejected_measurement = self.cli(*v2_correct_args, expect=2)
        self.assertEqual(rejected_measurement.stdout, "")
        self.assertIn("worker evidence_measurement must be exactly {}", rejected_measurement.stderr)
        false_measurement_answer_file.write_text(json.dumps(answer_obj), encoding="utf-8")
        v2_corrected_call = self.cli(*v2_correct_args)
        v2_corrected = json.loads(v2_corrected_call.stdout)
        expected_measurement = ATLAS._canonical_review_evidence_measurement(v2_initial)
        self.assertEqual(v2_corrected["structured_answer"]["evidence_measurement"], expected_measurement)
        self.assertEqual(v2_corrected_call.stdout, self.cli(*v2_correct_args).stdout)
        v2_accepted_review = dict(accepted_review, packet_sha256=v2_corrected["packet_sha256"])
        v2_accepted_review_file = self.root / "v2-accepted-review.json"
        v2_accepted_review_file.write_text(json.dumps(v2_accepted_review), encoding="utf-8")
        v2_corrected_file = self.root / "v2-corrected-review-packet.json"
        v2_corrected_file.write_text(v2_corrected_call.stdout, encoding="utf-8")
        v2_accept_args = ("answer-lifecycle", "accept", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                          "--packet-file", os.fspath(v2_corrected_file), "--review-file", os.fspath(v2_accepted_review_file))
        v2_final_bytes = self.cli(*v2_accept_args).stdout
        v2_final = json.loads(v2_final_bytes)
        self.assertEqual(v2_final["lifecycle_schema_version"], 2)
        self.assertEqual(v2_final["answer"]["evidence_measurement"], expected_measurement)
        self.assertEqual(v2_final_bytes, self.cli(*v2_accept_args).stdout)

        # A worker cannot authenticate a different value by rehashing the packet
        # and refreshing the review binding.
        for mutation in (
            {**expected_measurement, "measurement_schema_version": True},
            {**expected_measurement, "measurement_kind": "elapsed_time"},
            {**expected_measurement, "canonical_evidence_bytes": expected_measurement["canonical_evidence_bytes"] + 1},
            {**expected_measurement, "canonical_evidence_bytes": True},
            {**expected_measurement, "canonical_evidence_sha256": "0" * 64},
            {**expected_measurement, "unit": "provider tokens"},
            {**expected_measurement, "excluded_claims": list(reversed(expected_measurement["excluded_claims"]))},
            {**expected_measurement, "original_packet_sha256": "f" * 64},
            {**expected_measurement, "extra": "value"},
        ):
            tampered_packet = json.loads(v2_corrected_file.read_text(encoding="utf-8"))
            tampered_packet["structured_answer"]["evidence_measurement"] = mutation
            tampered_packet["packet_sha256"] = ATLAS._answer_packet_hash(tampered_packet)
            tampered_file = self.root / "v2-tampered-packet.json"
            tampered_file.write_text(json.dumps(tampered_packet), encoding="utf-8")
            updated_review = dict(v2_accepted_review, packet_sha256=tampered_packet["packet_sha256"])
            v2_accepted_review_file.write_text(json.dumps(updated_review), encoding="utf-8")
            tampered_accept = ("answer-lifecycle", "accept", "--db", os.fspath(self.db), "--repo", os.fspath(self.repo),
                               "--packet-file", os.fspath(tampered_file), "--review-file", os.fspath(v2_accepted_review_file))
            refusal = self.cli(*tampered_accept, expect=2)
            self.assertEqual(refusal.stdout, "")
            self.assertIn("does not match Atlas's exact measurement", refusal.stderr)
        v2_accepted_review_file.write_text(json.dumps(v2_accepted_review), encoding="utf-8")

        # Nested lifecycle versions and boolean aliases are refused, including
        # when the enclosing correction hash is recomputed.
        bad_lineage = json.loads(v2_correction_stdout)
        bad_lineage["original_packet"]["lifecycle_schema_version"] = 1
        bad_lineage["packet_sha256"] = ATLAS._answer_packet_hash(bad_lineage)
        bad_lineage_file = self.root / "v2-cross-version-correction.json"
        bad_lineage_file.write_text(json.dumps(bad_lineage), encoding="utf-8")
        self.assertEqual(self.cli("answer-lifecycle", "correct", "--correction-packet", os.fspath(bad_lineage_file),
                                  "--draft-file", os.fspath(corrected_draft), "--answer-file", os.fspath(answer_file), expect=2).stdout, "")
        with self.assertRaisesRegex(ATLAS.AtlasError, "integer 1 or 2"):
            ATLAS.answer_lifecycle("prepare", lifecycle_version=True)
        with self.assertRaisesRegex(ATLAS.AtlasError, "integer 1 or 2"):
            ATLAS.answer_lifecycle("prepare", lifecycle_version=3)

        rejected_corrected = dict(accepted_review, decision="rejected", rejection_reasons=[
            {"scope": "answer", "category": "unsupported_addition", "reason": "The corrected answer introduces an unsupported extra assertion.", "correction": "Remove the unsupported assertion from the answer."},
        ])
        accepted_file.write_text(json.dumps(rejected_corrected), encoding="utf-8")
        self.assertIn("second correction is not permitted", self.cli(*accept_args, expect=2).stderr)
        accepted_file.write_text(json.dumps(accepted_review), encoding="utf-8")

        second_correction_args = ("answer-lifecycle", "correct", "--correction-packet", os.fspath(corrected_packet_file),
                                  "--draft-file", os.fspath(corrected_draft), "--answer-file", os.fspath(answer_file))
        self.assertIn("versioned answer_correction", self.cli(*second_correction_args, expect=2).stderr)
        tampered = json.loads(correction_file.read_text())
        tampered["correction_round"] = 2
        correction_file.write_text(json.dumps(tampered), encoding="utf-8")
        self.assertEqual(self.cli(*correct_args, expect=2).stdout, "")
        correction_file.write_text(rejected_call.stdout, encoding="utf-8")

        source.write_text(source.read_text(encoding="utf-8") + "// changed after review\n", encoding="utf-8")
        self.assertIn("stale against current map, source, or receipt", self.cli(*accept_args, expect=2).stderr)
        self.assertIn("stale against current map, source, or receipt", self.cli(*v2_accept_args, expect=2).stderr)

    def test_captured_77_checkpoint_advances_to_deferred_final_map_only_after_all_routes(self):
        """Use the actual immutable 77-event task checkpoint, not a synthesized success fixture."""
        child = Path(os.environ.get("ATLAS_FINAL_MAP_CAPTURE", "/private/tmp/atlas-final-map-assembly-20261014/frozen-original77"))
        if not (child / "events/000077.json").is_file():
            self.skipTest("Immutable captured 77-event final-map fixture unavailable")
        events = [json.loads(path.read_bytes()) for path in sorted((child / "events").glob("*.json"))]
        plan = json.loads((child / "outputs/plan_author.json").read_bytes())
        self.assertEqual(len(events), 77)
        self.assertEqual(CONTINUATION._next_type(events, {"route_availability": []}, plan), "final_map_prepare")
        self.assertEqual(len(CONTINUATION._accepted_route_ids(events)), len(plan["ordered_work"]))
        self.assertEqual(len(plan["obligations"]), 6)
        self.assertFalse(any(event.get("type") == "final_map_accepted" for event in events))

    def test_synthetic_final_map_citation_and_obligation_corruption_is_rejected(self):
        """Synthetic corrupt-output checks; native Luna/Sol judgment is proven separately."""
        child = Path(os.environ.get("ATLAS_FINAL_MAP_CAPTURE", "/private/tmp/atlas-final-map-assembly-20261014/frozen-original77"))
        if not (child / "events/000077.json").is_file():
            self.skipTest("Immutable captured 77-event final-map fixture unavailable")
        plan_path = child / "outputs/plan_author.json"
        plan_raw = plan_path.read_bytes()
        plan = json.loads(plan_raw)
        evidence_id = "accepted-evidence-1"
        request = {"evidence_ids": [evidence_id],
                   "obligation_ids": [row["obligation_id"] for row in plan["obligations"]],
                   "history_tip_sha256": "a" * 64}
        context = {"task_sha256": plan["task_sha256"],
                   "source_identity_sha256": plan["source_identity_sha256"]}
        draft = {"schema_version": 1, "task_sha256": context["task_sha256"],
                 "source_identity_sha256": context["source_identity_sha256"],
                 "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
                 "history_tip_sha256": request["history_tip_sha256"], "title": "Reusable purchase-flow map",
                 "explanation": "A deliberately synthetic test draft with sufficient explanatory length for contract validation only, and no factual claim beyond the test fixture.",
                 "findings": [{"finding_id": "finding-1", "statement": "A synthetic statement with adequate detail for the validator.",
                               "evidence_refs": [evidence_id]}],
                 "obligations": [{"obligation_id": row["obligation_id"],
                                  "finding_ids": ["finding-1"] if i == 0 else [],
                                  "uncertainties": [] if i == 0 else ["Synthetic test gap remains unresolved."]}
                                 for i, row in enumerate(plan["obligations"])]}
        CONTINUATION._validate_final_map(draft, request, context, plan_raw)
        bad_citation = json.loads(json.dumps(draft))
        bad_citation["findings"][0]["evidence_refs"] = ["unaccepted-evidence"]
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "exact accepted evidence citation"):
            CONTINUATION._validate_final_map(bad_citation, request, context, plan_raw)
        missing_obligation = json.loads(json.dumps(draft))
        missing_obligation["obligations"].pop()
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "each original task obligation exactly once"):
            CONTINUATION._validate_final_map(missing_obligation, request, context, plan_raw)

    def test_synthetic_rejected_final_map_review_cannot_complete(self):
        """Synthetic rejection-state check; preserves accepted investigations and refuses completion."""
        child = Path(os.environ.get("ATLAS_FINAL_MAP_CAPTURE", "/private/tmp/atlas-final-map-assembly-20261014/frozen-original77"))
        if not (child / "events/000077.json").is_file():
            self.skipTest("Immutable captured 77-event final-map fixture unavailable")
        events = [json.loads(path.read_bytes()) for path in sorted((child / "events").glob("*.json"))]
        plan = json.loads((child / "outputs/plan_author.json").read_bytes())
        events.append({"type": "final_map_review_completed", "payload": {"decision": "rejected"}})
        self.assertEqual(CONTINUATION._next_type(events, {"route_availability": []}, plan), "final_map_feedback_prepare")

    def test_synthetic_public_rejected_final_map_prepares_one_bounded_feedback_step(self):
        """Synthetic routing proof: exact rejection selects one bounded correction, no worker call."""
        child = Path(os.environ.get("ATLAS_FINAL_MAP_CAPTURE", "/private/tmp/atlas-final-map-assembly-20261014/frozen-original77"))
        if not (child / "events/000077.json").is_file():
            self.skipTest("Immutable captured 77-event final-map fixture unavailable")
        events = [json.loads(path.read_bytes()) for path in sorted((child / "events").glob("*.json"))]
        events.append({"type": "final_map_review_completed", "payload": {"decision": "rejected"}})
        context = json.loads((child / "context.json").read_bytes())
        plan = json.loads((child / "outputs/plan_author.json").read_bytes())
        self.assertEqual(CONTINUATION._next_type(events, context, plan), "final_map_feedback_prepare")
        real_next = CONTINUATION._next_type
        calls = []
        def bounded_next(*args):
            calls.append(True)
            if len(calls) > 1:
                raise AssertionError("rejected final review reentered the dispatch loop")
            return real_next(*args)
        expected = {"status": "final_map_feedback_prepare", "task_complete": False}
        with mock.patch.object(CONTINUATION, "_ensure_engine"), \
             mock.patch.object(CONTINUATION, "_load", return_value=(context, events)), \
             mock.patch.object(CONTINUATION, "_events", return_value=events), \
             mock.patch.object(CONTINUATION, "_next_type", side_effect=bounded_next), \
             mock.patch.object(CONTINUATION, "_prepare_final_map_feedback_revision") as prepare_feedback, \
             mock.patch.object(CONTINUATION, "status", return_value=expected) as status_call, \
             mock.patch.object(CONTINUATION, "_worker_value", side_effect=AssertionError("unexpected redispatch")) as worker:
            result = CONTINUATION.resume("unused", "unused", "unused", "unused", str(child), prepare_only=True)
        self.assertEqual(result, expected)
        self.assertEqual(len(calls), 1)
        prepare_feedback.assert_called_once()
        status_call.assert_called_once()
        worker.assert_not_called()

    def test_synthetic_rejected_corrective_review_is_terminal(self):
        """The one permitted corrective review cannot loop back to its author or reviewer."""
        child = Path(os.environ.get("ATLAS_FINAL_MAP_CAPTURE", "/private/tmp/atlas-final-map-assembly-20261014/frozen-original77"))
        if not (child / "events/000077.json").is_file():
            self.skipTest("Immutable captured 77-event final-map fixture unavailable")
        events = [json.loads(path.read_bytes()) for path in sorted((child / "events").glob("*.json"))]
        events.extend([
            {"type": "final_map_review_completed", "payload": {"decision": "rejected"}},
            {"type": "final_map_feedback_revision_prepared", "payload": {"revision": 1}},
            {"type": "final_map_revision_author_validated", "payload": {"revision": 1}},
            {"type": "final_map_revision_review_input_prepared", "payload": {"revision": 1}},
            {"type": "final_map_revision_review_completed", "payload": {"revision": 1, "decision": "rejected"}},
        ])
        context = json.loads((child / "context.json").read_bytes())
        plan = json.loads((child / "outputs/plan_author.json").read_bytes())
        self.assertEqual(CONTINUATION._next_type(events, context, plan), "final_map_rejected")
        expected = {"status": "final_map_rejected", "task_complete": False}
        with mock.patch.object(CONTINUATION, "_ensure_engine"), \
             mock.patch.object(CONTINUATION, "_load", return_value=(context, events)), \
             mock.patch.object(CONTINUATION, "_events", return_value=events), \
             mock.patch.object(CONTINUATION, "_next_type", return_value="final_map_rejected"), \
             mock.patch.object(CONTINUATION, "status", return_value=expected) as status_call, \
             mock.patch.object(CONTINUATION, "_worker_value", side_effect=AssertionError("unexpected redispatch")) as worker:
            result = CONTINUATION.resume("unused", "unused", "unused", "unused", str(child))
        self.assertEqual(result, expected)
        status_call.assert_called_once()
        worker.assert_not_called()

    def test_public_resume_finalizes_saved_accepted_review_once_for_both_branches(self):
        """Captured 77/84 lineage: after accepted review commit, public resume verifies and finalizes once."""
        capture_root = Path(os.environ.get("ATLAS_FINALIZATION_CAPTURE_ROOT",
            "/private/tmp/atlas-final-map-assembly-20261015/prototype3-proof/accepted-review-finalization-defect-trial"))
        if (not (capture_root / "native77-task/events/000079.json").is_file()
                or not (capture_root / "native84-task/events/000086.json").is_file()):
            self.skipTest("Prepared captured 77/84 final-map checkpoints unavailable")
        for name, expected_count in (("native77-task", 79), ("native84-task", 86)):
            self.assertEqual(len(list((capture_root / name / "events").glob("*.json"))), expected_count,
                "Finalization regression requires the exact immutable prepared checkpoint")
        repo = "/Users/kamenkamenov/taggable-api"
        db = "/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite"
        task_file = "/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt"
        intake_run = "/private/tmp/atlas-discount-lifecycle-task-20261012/run"

        def pending_acceptance(branch, decision="accepted", tamper=False):
            source = capture_root / ("native77-task" if branch == "initial" else "native84-task")
            root = self.root / f"pending-{branch}-{decision}-{'tampered' if tamper else 'clean'}"
            shutil.copytree(source, root)
            plan, _ = CONTINUATION._read_json(root / "outputs/plan_author.json", "captured accepted plan")
            context, _ = CONTINUATION._read_json(root / "context.json", "captured task context")
            manifest, _ = CONTINUATION._read_json(root / "manifest.json", "captured run manifest")
            context["strategy"] = manifest["strategy"]
            revision = branch == "revision"
            author_path = "inputs/final-map-author-revision-0001.json" if revision else "inputs/final-map-author.json"
            author_request, _ = CONTINUATION._read_json(root / author_path, "captured author request")
            evidence_id = author_request["evidence_ids"][0]
            finding_id = "synthetic-finalization-finding"
            draft = {"schema_version": 1, "task_sha256": author_request["task_sha256"],
                "source_identity_sha256": author_request["source_identity_sha256"], "plan_sha256": author_request["plan_sha256"],
                "history_tip_sha256": author_request["history_tip_sha256"], "title": "Synthetic resume proof map",
                "explanation": "Synthetic test evidence exercises interrupted finalization only and makes no real-task completeness claim.",
                "findings": [{"finding_id": finding_id, "statement": "Synthetic finding for production acceptance-boundary checks only.",
                    "evidence_refs": [evidence_id]}],
                "obligations": [{"obligation_id": row["obligation_id"], "finding_ids": [finding_id],
                    "uncertainties": ["Synthetic evidence does not resolve factual adequacy."]} for row in plan["obligations"]]}
            draft_raw = CONTINUATION._json_bytes(draft)
            explanation_raw = draft["explanation"].encode("utf-8")
            draft_path = "outputs/final-map-revision-0001.json" if revision else "outputs/final-map.json"
            explanation_path = "outputs/final-map-revision-0001.txt" if revision else "outputs/final-map.txt"
            draft_ref = CONTINUATION._artifact(root, draft_path, draft_raw)
            explanation_ref = CONTINUATION._artifact(root, explanation_path, explanation_raw)
            phase = "final_map_author_revision_0001" if revision else "final_map_author"
            author_thread = f"synthetic-{branch}-author-thread"
            CONTINUATION._append(root, f"{phase}_worker_completed", {"phase": phase, "worker_thread_id": author_thread})
            validation_type = "final_map_revision_author_validated" if revision else "final_map_author_validated"
            CONTINUATION._append(root, validation_type, {"task_sha256": context["task_sha256"],
                "source_identity_sha256": context["source_identity_sha256"], "plan_sha256": author_request["plan_sha256"],
                "history_tip_sha256": author_request["history_tip_sha256"], "map_sha256": hashlib.sha256(draft_raw).hexdigest()},
                [draft_ref, explanation_ref])
            current_events = CONTINUATION._events(root)
            CONTINUATION._prepare_final_map_review(root, context, plan, current_events)
            review_phase = "final_map_review_revision_0001" if revision else "final_map_review"
            review_path = "inputs/final-map-review-revision-0001.json" if revision else "inputs/final-map-review.json"
            review_request, review_request_raw = CONTINUATION._read_json(root / review_path, "prepared review request")
            judgments = [{"obligation_id": row["obligation_id"],
                "decision": ("supported" if decision == "accepted" else "gap_explicit"),
                "finding_ids": ([finding_id] if decision == "accepted" else []),
                "uncertainty": "Synthetic review judgment; no real acceptance is implied."}
                for row in draft["obligations"]]
            review = {"decision": decision, "reviewer_identity": review_request["reviewer_identity"],
                "task_sha256": review_request["task_sha256"], "source_identity_sha256": review_request["source_identity_sha256"],
                "plan_sha256": review_request["plan_sha256"], "map_sha256": review_request["map_sha256"],
                "finding_link_policy": review_request["finding_link_policy"],
                "obligation_judgments": judgments,
                "basis": "Synthetic accepted decision exists only to test interrupted finalization recovery boundaries."}
            review_raw = CONTINUATION._json_bytes(review)
            review_artifact = "outputs/final-map-review-revision-0001.json" if revision else "outputs/final-map-review.json"
            review_artifact_ref = CONTINUATION._artifact(root, review_artifact, review_raw)
            review_thread = f"synthetic-{branch}-review-thread"
            CONTINUATION._append(root, f"{review_phase}_worker_completed", {"phase": review_phase, "worker_thread_id": review_thread})
            request_rel = review_path
            CONTINUATION._append(root, "final_map_revision_review_completed" if revision else "final_map_review_completed",
                {"decision": decision, "task_sha256": context["task_sha256"],
                 "source_identity_sha256": context["source_identity_sha256"], "plan_sha256": review_request["plan_sha256"],
                 "history_tip_sha256": review_request["history_tip_sha256"], "map_sha256": review_request["map_sha256"]},
                [review_artifact_ref, {"path": request_rel, "sha256": hashlib.sha256(review_request_raw).hexdigest(),
                                       "bytes": len(review_request_raw)}])
            if tamper:
                (root / ("outputs/final-map-preservation-review-revision-0001.json" if revision
                         else "outputs/final-map-preservation-review.json")).write_bytes(b"tampered receipt")
            return root, context, plan, author_thread, review_thread

        for branch in ("initial", "revision"):
            with self.subTest(branch=branch):
                root, context, plan, _author_thread, _review_thread = pending_acceptance(branch)
                verify_calls = []
                def verify_native(_root, request, event, role, model, phase):
                    verify_calls.append((role, phase))
                    self.assertEqual(event.get("type"), phase + "_worker_completed")
                    self.assertEqual(role, "luna_draft" if "author" in phase else "sol_review")
                    self.assertEqual(model, "gpt-6-luna" if role == "luna_draft" else "gpt-6.1-sol")
                def load_current(*_args, **_kwargs):
                    return context, CONTINUATION._events(root)
                status_args = (repo, db, task_file, intake_run, str(root))
                with mock.patch.object(CONTINUATION, "_ensure_engine"), \
                     mock.patch.object(CONTINUATION, "_load", side_effect=load_current), \
                     mock.patch.object(CONTINUATION, "_verify_final_map_worker", side_effect=verify_native), \
                     mock.patch.object(CONTINUATION, "_worker_value", side_effect=AssertionError("finalization redispatched a worker")):
                    first = CONTINUATION.resume(*status_args, prepare_only=True)
                    self.assertEqual(first["status"], "completed")
                    accepted = [event for event in CONTINUATION._events(root) if event.get("type") == "final_map_accepted"]
                    self.assertEqual(len(accepted), 1)
                    snapshot = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in root.rglob("*") if path.is_file()}
                    second = CONTINUATION.resume(*status_args, prepare_only=True)
                    self.assertEqual(second["status"], "completed")
                    self.assertEqual(snapshot, {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in root.rglob("*") if path.is_file()})
                    self.assertEqual(len([event for event in CONTINUATION._events(root)
                        if event.get("type") == "final_map_accepted"]), 1)
                self.assertTrue(verify_calls)

        rejected_root, rejected_context, _plan, _, _ = pending_acceptance("revision", decision="rejected")
        rejected_context["strategy"] = CONTINUATION._read_json(rejected_root / "manifest.json", "captured manifest")[0]["strategy"]
        rejected_args = ("/Users/kamenkamenov/taggable-api",
            "/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite",
            "/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt",
            "/private/tmp/atlas-discount-lifecycle-task-20261012/run", str(rejected_root))
        with mock.patch.object(CONTINUATION, "_ensure_engine"), \
             mock.patch.object(CONTINUATION, "_load", side_effect=lambda *_, **__: (rejected_context, CONTINUATION._events(rejected_root))), \
             mock.patch.object(CONTINUATION, "_final_map_finalize", side_effect=AssertionError("rejected review finalized")), \
             mock.patch.object(CONTINUATION, "_worker_value", side_effect=AssertionError("rejected review redispatched")):
            rejected_status = CONTINUATION.resume(*rejected_args, prepare_only=True)
        self.assertEqual(rejected_status["status"], "final_map_rejected")
        self.assertFalse(any(event.get("type") == "final_map_accepted" for event in CONTINUATION._events(rejected_root)))

        tampered_root, tampered_context, _, _, _ = pending_acceptance("initial", tamper=True)
        tampered_context["strategy"] = CONTINUATION._read_json(tampered_root / "manifest.json", "captured manifest")[0]["strategy"]
        tampered_args = ("/Users/kamenkamenov/taggable-api",
            "/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite",
            "/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt",
            "/private/tmp/atlas-discount-lifecycle-task-20261012/run", str(tampered_root))
        with mock.patch.object(CONTINUATION, "_ensure_engine"), \
             mock.patch.object(CONTINUATION, "_load", side_effect=lambda *_, **__: (tampered_context, CONTINUATION._events(tampered_root))), \
             mock.patch.object(CONTINUATION, "_worker_value", side_effect=AssertionError("tampered review redispatched")):
            with self.assertRaisesRegex(CONTINUATION.ContinuationError, "artifact changed"):
                CONTINUATION.resume(*tampered_args, prepare_only=True)
        self.assertFalse(any(json.loads(path.read_bytes()).get("type") == "final_map_accepted"
            for path in sorted((tampered_root / "events").glob("*.json"))))

    def test_synthetic_final_map_worker_artifact_tamper_is_rejected(self):
        """Synthetic native-job artifact check; terminal admission is explicitly simulated."""
        root = self.root
        phase = "final_map_author"
        job = root / "workers" / phase
        request, result, event, register_path, register_sha, digests = self.synthetic_native_final_worker(
            root, phase, "luna_draft", "gpt-6-luna")
        cli_path = root / "pinned-cli"
        patches = self.synthetic_native_admission(root, cli_path)
        with patches[0], patches[1], patches[2]:
            CONTINUATION._verify_final_map_worker(root, request, event, "luna_draft", "gpt-6-luna", phase)
            (job / "schema.json").write_bytes(b'{"type":"string"}')
            with self.assertRaisesRegex(CONTINUATION.ContinuationError, "artifact changed: schema.json"):
                CONTINUATION._verify_final_map_worker(root, request, event, "luna_draft", "gpt-6-luna", phase)

    def test_synthetic_native_orphan_recovery_uses_register_without_redispatch_for_both_roles(self):
        """Synthetic provider edges exercise production recovery; terminal admission is simulated."""
        for phase, role, model in (("final_map_author", "luna_draft", "gpt-6-luna"),
                                   ("final_map_review", "sol_review", "gpt-6.1-sol"),
                                   ("final_map_author_revision_0001", "luna_draft", "gpt-6-luna"),
                                   ("final_map_review_revision_0001", "sol_review", "gpt-6.1-sol")):
            with self.subTest(phase=phase):
                root = self.root / phase
                root.mkdir()
                request, _result, _event, register, register_sha, _digests = self.synthetic_native_final_worker(
                    root, phase, role, model)
                (root / "outputs" / f"{phase}.txt").unlink()
                (root / "outputs" / f"{phase}-worker.json").unlink()
                fake_append = mock.Mock(side_effect=lambda _root, event_type, payload, refs: {
                    "type": event_type, "payload": payload, "artifacts": refs})
                patches = self.synthetic_native_admission(root, root / "pinned-cli")
                with mock.patch.object(CONTINUATION, "_revalidate_bound_engine"), \
                     mock.patch.object(CONTINUATION, "_events", return_value=[]), \
                     mock.patch.object(CONTINUATION, "_final_map_request_binding", return_value=(request, {}, b"{}")), \
                     mock.patch.object(CONTINUATION, "_append", fake_append), \
                     mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=AssertionError("redispatch")) as dispatch, \
                     patches[0], patches[1], patches[2]:
                    value, event = CONTINUATION._worker_value(root, role, request["prompt"], request["schema"],
                        phase, 10, {}, os.fspath(register), register_sha)
                self.assertEqual(value, {})
                self.assertEqual(event["type"], f"{phase}_worker_completed")
                self.assertEqual(event["payload"]["recovered_from_register_sha256"], register_sha)
                dispatch.assert_not_called()
                fake_append.assert_called_once()
                self.assertEqual(fake_append.call_args.args[1], f"{phase}_worker_completed")

    def test_legacy_completed_worker_recovery_scope_remains_unchanged(self):
        """The captured legacy-register lane remains restricted to its original Sol map-review phase."""
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "limited to the pending Sol map review"):
            CONTINUATION._recover_completed_worker(self.root, {}, "luna_draft", "", {},
                                                   "final_map_author", "", "")

    def test_synthetic_cached_final_worker_tamper_refuses_before_consumption_for_both_roles(self):
        """Synthetic cached completions: missing/tampered native files cannot reach validation or acceptance."""
        for phase, role, model in (("final_map_author", "luna_draft", "gpt-6-luna"),
                                   ("final_map_review", "sol_review", "gpt-6.1-sol"),
                                   ("final_map_author_revision_0001", "luna_draft", "gpt-6-luna"),
                                   ("final_map_review_revision_0001", "sol_review", "gpt-6.1-sol")):
            with self.subTest(phase=phase):
                root = self.root / phase
                root.mkdir()
                request, _result, event, _register, _register_sha, _digests = self.synthetic_native_final_worker(
                    root, phase, role, model)
                (root / "workers" / phase / "cli-schema.json").unlink()
                patches = self.synthetic_native_admission(root, root / "pinned-cli")
                with mock.patch.object(CONTINUATION, "_revalidate_bound_engine"), \
                     mock.patch.object(CONTINUATION, "_events", return_value=[event]), \
                     mock.patch.object(CONTINUATION, "_final_map_request_binding", return_value=(request, {}, b"{}")), \
                     mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=AssertionError("redispatch")) as dispatch, \
                     patches[0], patches[1], patches[2]:
                    with self.assertRaisesRegex(CONTINUATION.ContinuationError, "missing files or contains an unexpected entry"):
                        CONTINUATION._worker_value(root, role, request["prompt"], request["schema"], phase,
                                                   10, {}, None, None)
                dispatch.assert_not_called()
                self.assertFalse((root / "outputs" / "final_map_accepted.json").exists())

    def test_synthetic_fresh_final_worker_tamper_refuses_before_answer_artifacts_for_both_roles(self):
        """Synthetic provider edges prove failed native integrity cannot write parent answer artifacts."""
        for phase, role, model in (("final_map_author", "luna_draft", "gpt-6-luna"),
                                   ("final_map_review", "sol_review", "gpt-6.1-sol"),
                                   ("final_map_author_revision_0001", "luna_draft", "gpt-6-luna"),
                                   ("final_map_review_revision_0001", "sol_review", "gpt-6.1-sol")):
            with self.subTest(phase=phase):
                root = self.root / phase
                root.mkdir(); (root / "inputs").mkdir()
                request, input_name = ({"role": role, "prompt": f"synthetic exact prompt for {phase}",
                    "schema": {"type": "object"}, "task_sha256": "a" * 64,
                    "source_identity_sha256": "b" * 64, "plan_sha256": "c" * 64,
                    "history_tip_sha256": "d" * 64},
                    {"final_map_author": "final-map-author.json", "final_map_review": "final-map-review.json",
                     "final_map_author_revision_0001": "final-map-author-revision-0001.json",
                     "final_map_review_revision_0001": "final-map-review-revision-0001.json"}[phase])
                (root / "inputs" / input_name).write_text(json.dumps(request), encoding="utf-8")
                (root / "pinned-cli").write_bytes(b"synthetic pinned CLI fingerprint")
                (root / "pinned-cli").chmod(0o755)
                def completed_then_tampered(worker_role, prompt, job_path, timeout_seconds, output_schema):
                    _request, result, _event, _register, _sha, _digests = self.synthetic_native_final_worker(
                        root, phase, role, model)
                    (root / "outputs" / f"{phase}.txt").unlink()
                    (root / "outputs" / f"{phase}-worker.json").unlink()
                    (root / "workers" / phase / "cli-schema.json").unlink()
                    return {**result, "final_text": "{}"}
                patches = self.synthetic_native_admission(root, root / "pinned-cli")
                with mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=completed_then_tampered) as dispatch, \
                     mock.patch.object(CONTINUATION, "_append") as append, patches[0], patches[1], patches[2]:
                    with self.assertRaisesRegex(CONTINUATION.ContinuationError, "missing files or contains an unexpected entry"):
                        CONTINUATION._record_worker(root, role, request["prompt"], request["schema"], phase, 10)
                dispatch.assert_called_once()
                append.assert_not_called()
                self.assertFalse((root / "outputs" / f"{phase}.txt").exists())
                self.assertFalse((root / "outputs" / f"{phase}-worker.json").exists())

    def test_synthetic_review_prompt_aligns_gap_with_rejection_and_supported_with_acceptance(self):
        """Synthetic request/draft contract: unanswered obligations reject; fully supported obligations can pass."""
        child = Path(os.environ.get("ATLAS_FINAL_MAP_CAPTURE", "/private/tmp/atlas-final-map-assembly-20261014/frozen-original77"))
        if not (child / "events/000077.json").is_file():
            self.skipTest("Immutable captured 77-event final-map fixture unavailable")
        root = self.root
        (root / "inputs").mkdir(); (root / "outputs").mkdir()
        plan_path = child / "outputs/plan_author.json"
        plan_raw = plan_path.read_bytes()
        plan = json.loads(plan_raw)
        context = {"task_sha256": plan["task_sha256"], "source_identity_sha256": plan["source_identity_sha256"],
                   "task_text": Path(os.environ.get("ATLAS_FINAL_MAP_TASK", "/private/tmp/atlas-final-map-assembly-20261014/original-task.txt")).read_text()}
        evidence_id = "accepted-source:evidence.json"
        history_tip = "e" * 64
        author_request = {"role": "luna_draft", "task_sha256": context["task_sha256"],
            "source_identity_sha256": context["source_identity_sha256"], "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
            "history_tip_sha256": history_tip, "evidence_ids": [evidence_id],
            "obligation_ids": [row["obligation_id"] for row in plan["obligations"]],
            "evidence": [{"evidence_id": evidence_id, "content": "synthetic evidence"}]}
        draft = {"schema_version": 1, "task_sha256": context["task_sha256"],
            "source_identity_sha256": context["source_identity_sha256"], "plan_sha256": author_request["plan_sha256"],
            "history_tip_sha256": history_tip, "title": "Synthetic reviewed map",
            "explanation": "This is a synthetic contract-only explanation with more than one hundred characters to exercise the exact validator without asserting any original task facts.",
            "findings": [{"finding_id": "f1", "statement": "A sufficiently detailed synthetic finding for validator coverage.",
                          "evidence_refs": [evidence_id]},
                         {"finding_id": "f2", "statement": "A second sufficiently detailed synthetic finding for linkage validation.",
                          "evidence_refs": [evidence_id]}],
            "obligations": [{"obligation_id": row["obligation_id"], "finding_ids": ["f1" if index == 0 else "f2"],
                             "uncertainties": ["A bounded implementation detail remains uncertain."]}
                            for index, row in enumerate(plan["obligations"])]}
        (root / "inputs/final-map-author.json").write_text(json.dumps(author_request), encoding="utf-8")
        (root / "outputs/plan_author.json").write_bytes(plan_raw)
        draft_raw = json.dumps(draft, sort_keys=True, separators=(",", ":")).encode()
        (root / "outputs/final-map.json").write_bytes(draft_raw)
        explanation_raw = draft["explanation"].encode("utf-8")
        (root / "outputs/final-map.txt").write_bytes(explanation_raw)
        validated = {"type": "final_map_author_validated", "payload": {"map_sha256": hashlib.sha256(draft_raw).hexdigest()},
            "artifacts": [{"path": "outputs/final-map.json", "sha256": hashlib.sha256(draft_raw).hexdigest(), "bytes": len(draft_raw)},
                          {"path": "outputs/final-map.txt", "sha256": hashlib.sha256(explanation_raw).hexdigest(), "bytes": len(explanation_raw)},
                          {"path": "inputs/final-map-author.json", "sha256": hashlib.sha256((root / "inputs/final-map-author.json").read_bytes()).hexdigest(),
                           "bytes": (root / "inputs/final-map-author.json").stat().st_size}]}
        with mock.patch.object(CONTINUATION, "_events", return_value=[validated]), \
             mock.patch.object(CONTINUATION, "_append", return_value={"type": "final_map_review_input_prepared"}):
            CONTINUATION._prepare_final_map_review(root, context, plan, [validated])
        # Simulate a crash after the receipt was committed but before the review request event.
        request_path = root / "inputs/final-map-review.json"
        request_path.unlink()
        receipt_path = root / "outputs/final-map-preservation-review.json"
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        receipt_event = {"type": "final_map_review_preservation_prepared",
            "payload": {"receipt_sha256": hashlib.sha256(receipt_raw).hexdigest()},
            "artifacts": [{"path": row["path"], "sha256": row["sha256"], "bytes": row["bytes"]}
                          for row in receipt["artifacts"]]}
        with mock.patch.object(CONTINUATION, "_events", return_value=[validated, receipt_event]), \
             mock.patch.object(CONTINUATION, "_append", return_value={"type": "final_map_review_input_prepared"}) as append:
            CONTINUATION._prepare_final_map_review(root, context, plan, [validated, receipt_event])
        append.assert_called_once()
        self.assertTrue(request_path.is_file())
        request = json.loads((root / "inputs/final-map-review.json").read_bytes())
        self.assertIn("set the overall decision to rejected", request["prompt"])
        self.assertIn("Policy whole_map_known_findings_v1", request["prompt"])
        self.assertIn("Assess separately whether the author made important relationships and synthesis clear", request["prompt"])
        self.assertIn("reviewer findings must not silently repair the map", request["prompt"])
        self.assertEqual(request["finding_link_policy"], "whole_map_known_findings_v1")
        per_obligation = request["schema"]["properties"]["obligation_judgments"]["items"]["anyOf"]
        self.assertEqual({branch["properties"]["obligation_id"]["const"] for branch in per_obligation},
                         {row["obligation_id"] for row in draft["obligations"]})
        all_finding_ids = {row["finding_id"] for row in draft["findings"]}
        self.assertTrue(all(branch["properties"]["finding_ids"]["items"]["enum"] == sorted(all_finding_ids)
                            for branch in per_obligation))
        cli_schema = CONTINUATION.route_autorun._cli_schema(request["schema"])
        cli_branches = cli_schema["properties"]["obligation_judgments"]["items"]["anyOf"]
        self.assertEqual({branch["properties"]["obligation_id"]["const"] for branch in cli_branches},
                         {row["obligation_id"] for row in draft["obligations"]})
        empty_variant = CONTINUATION._final_map_judgment_variants([
            {"obligation_id": "explicit_gap", "finding_ids": []}])[0]
        self.assertEqual(empty_variant["properties"]["finding_ids"], {"type": "array", "maxItems": 0})
        supported = {"decision": "accepted", "reviewer_identity": request["reviewer_identity"],
            "task_sha256": request["task_sha256"], "source_identity_sha256": request["source_identity_sha256"],
            "plan_sha256": request["plan_sha256"], "map_sha256": request["map_sha256"],
            "finding_link_policy": request["finding_link_policy"],
            "obligation_judgments": [{"obligation_id": row["obligation_id"], "decision": "supported",
                "finding_ids": ["f1" if index == 0 else "f2"], "uncertainty": "A bounded implementation detail remains uncertain."}
                for index, row in enumerate(plan["obligations"])], "basis": "Synthetic independent source judgment sufficient for contract validation."}
        CONTINUATION._validate_final_map_review(supported, draft, request)
        cross_link = json.loads(json.dumps(supported))
        cross_link["obligation_judgments"][0]["finding_ids"] = ["f1", "f2"]
        CONTINUATION._validate_final_map_review(cross_link, draft, request)
        unknown_link = json.loads(json.dumps(supported))
        unknown_link["obligation_judgments"][0]["finding_ids"] = ["not-in-map"]
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "obligation judgment is malformed"):
            CONTINUATION._validate_final_map_review(unknown_link, draft, request)
        # The exact historical no-policy request retains the prior authored-link subset rule.
        legacy_request = {key: value for key, value in request.items() if key != "finding_link_policy"}
        legacy_response = {key: value for key, value in supported.items() if key != "finding_link_policy"}
        with self.assertRaisesRegex(CONTINUATION.FinalMapLinkageError, "links outside the exact obligation evidence"):
            CONTINUATION._validate_final_map_review(legacy_response | {
                "obligation_judgments": cross_link["obligation_judgments"]}, draft, legacy_request)
        mixed_invalid = json.loads(json.dumps(cross_link))
        mixed_invalid["obligation_judgments"][1]["decision"] = "supported"
        mixed_invalid["obligation_judgments"][1]["finding_ids"] = []
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "lacks required obligation support"):
            CONTINUATION._validate_final_map_review(mixed_invalid, draft, request)
        gap = json.loads(json.dumps(supported))
        gap["decision"] = "rejected"
        gap["obligation_judgments"][0] = {"obligation_id": plan["obligations"][0]["obligation_id"],
            "decision": "gap_explicit", "finding_ids": [], "uncertainty": "The captured evidence does not resolve this exact obligation."}
        CONTINUATION._validate_final_map_review(gap, draft, request)
        gap["decision"] = "accepted"
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "cannot complete a map with an unanswered original obligation"):
            CONTINUATION._validate_final_map_review(gap, draft, request)

    def test_invalid_completed_revision_review_has_one_append_only_retry_route(self):
        plan = {"follow_up_work": [{"follow_up_id": "assemble_reusable_map", "execution_state": "deferred"}]}
        context = {}
        invalid = [{"type": "final_map_revision_review_linkage_rejected", "payload": {"decision": "rejected"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(invalid, context, plan),
                         "final_map_revision_review_retry_prepare")
        prepared = invalid + [{"type": "final_map_revision_review_retry_input_prepared"}]
        self.assertEqual(CONTINUATION._final_map_next_type(prepared, context, plan),
                         "final_map_review_revision_retry_0001")
        accepted = prepared + [{"type": "final_map_revision_review_retry_completed",
                                "payload": {"decision": "accepted"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(accepted, context, plan), "final_map_finalize")
        accepted_binding = CONTINUATION._final_map_acceptance_review_binding(accepted[-1], accepted)
        self.assertEqual(accepted_binding, {"review_phase": "final_map_review_revision_retry_0001", "revision": 1})
        rejected = prepared + [{"type": "final_map_revision_review_retry_completed",
                                "payload": {"decision": "rejected"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(rejected, context, plan),
                         "final_map_feedback_revision_0002_prepare")
        second = rejected + [{"type": "final_map_feedback_revision_0002_prepared"},
            {"type": "final_map_revision_0002_author_validated"},
            {"type": "final_map_revision_0002_review_input_prepared"}]
        self.assertEqual(CONTINUATION._final_map_next_type(second, context, plan),
                         "final_map_review_revision_0002")
        second_rejected = second + [{"type": "final_map_revision_0002_review_completed",
                                     "payload": {"decision": "rejected"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(second_rejected, context, plan), "final_map_citation_additions_prepare")
        citation = second_rejected + [{"type": "final_map_citation_revision_prepared"},
            {"type": "final_map_citation_author_validated"},
            {"type": "final_map_citation_review_input_prepared"}]
        self.assertEqual(CONTINUATION._final_map_next_type(citation, context, plan), "final_map_review_citation_0001")
        citation_rejected = citation + [{"type": "final_map_citation_review_completed", "payload": {"decision": "rejected"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(citation_rejected, context, plan), "final_map_rejected")
        citation_accepted = citation + [{"type": "final_map_citation_review_completed",
            "payload": {"decision": "accepted", "review_phase": "final_map_review_citation_0001"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(citation_accepted, context, plan), "final_map_finalize")
        self.assertEqual(CONTINUATION._final_map_acceptance_review_binding(citation_accepted[-1], citation_accepted),
            {"review_phase": "final_map_review_citation_0001", "revision": 1})
        # A prepared versioned attempt cannot silently fall back to the historical
        # no-attempt binding; the exact legacy request above remains valid.
        versioned = [{"type": "final_map_citation_additions_prepared", "payload": {"attempt": 1}},
            {"type": "final_map_citation_additions_assembled", "payload": {"attempt": 1}},
            {"type": "final_map_citation_review_input_prepared", "payload": {"attempt": 1}},
            {"type": "final_map_citation_review_completed", "payload": {"decision": "accepted"}}]
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "missing its required attempt identity"):
            CONTINUATION._citation_review_attempt(versioned, versioned[-1])
        versioned[-1]["payload"]["attempt"] = 2
        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "exact prepared and assembled attempt"):
            CONTINUATION._citation_review_attempt(versioned, versioned[-1])
        attempt_two_assembly = {"payload": {"attempt": 2, "proposal_sha256": "proposal-2",
            "proposal_request_sha256": "request-2", "base_map_sha256": "base-2",
            "catalogue_sha256": "catalogue", "assembly": "assembly-2"}}
        review_two_request = {"citation_additions_provenance": {
            key: attempt_two_assembly["payload"][key] for key in
            ("attempt", "proposal_sha256", "proposal_request_sha256", "base_map_sha256", "catalogue_sha256", "assembly")}}
        self.assertIsNone(CONTINUATION._require_citation_additions_provenance(review_two_request, attempt_two_assembly))
        review_two_request["citation_additions_provenance"]["attempt"] = 1
        review_two_request["citation_additions_provenance"]["proposal_sha256"] = "proposal-1"
        with self.assertRaisesRegex(CONTINUATION.ContinuationError,
                "mixes proposal or assembly provenance from another attempt"):
            CONTINUATION._require_citation_additions_provenance(review_two_request, attempt_two_assembly)
        self.assertEqual(CONTINUATION._final_map_next_type(second_rejected, context, plan), "final_map_citation_additions_prepare")
        second_accepted = second[:-1] + [{"type": "final_map_revision_0002_review_completed",
                                         "payload": {"decision": "accepted",
                                                     "review_phase": "final_map_review_revision_0002"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(second_accepted, context, plan), "final_map_finalize")
        self.assertEqual(CONTINUATION._final_map_acceptance_review_binding(second_accepted[-1], second_accepted),
                         {"review_phase": "final_map_review_revision_0002", "revision": 2})

    def test_captured106_historical_citation_request_keeps_its_exact_contract(self):
        """The saved attempt-less full-map request remains verifiable as legacy evidence."""
        fixture = Path("/private/tmp/atlas-final-map-assembly-20261015/prototype5-proof/frozen-original106-schema-failure")
        if not (fixture / "events/000106.json").is_file():
            self.skipTest("Immutable captured106 schema-failure fixture unavailable")
        events = CONTINUATION._events(fixture)
        self.assertEqual(events[-1]["type"], "final_map_citation_revision_prepared")
        request, raw = CONTINUATION._read_json(fixture / "inputs/final-map-author-citation-0001.json", "historical author request")
        context, _ = CONTINUATION._read_json(fixture / "context.json", "captured context")
        plan, plan_raw = CONTINUATION._read_json(fixture / "outputs/plan_author.json", "captured plan")
        base, _ = CONTINUATION._read_json(fixture / "outputs/final-map-revision-0002.json", "rejected base map")
        self.assertNotIn("attempt", request)
        self.assertEqual(CONTINUATION._sha(raw), CONTINUATION._CITATION_SCHEMA_FAILURE_REQUEST_SHA256)
        self.assertEqual(request["schema"], CONTINUATION._legacy_final_map_citation_schema(
            context, plan, base, request["evidence_ids"]))
        self.assertEqual(events[-1]["payload"]["request_sha256"], CONTINUATION._sha(raw))
        CONTINUATION._final_map_request_binding(fixture, context, "luna_draft", request["prompt"],
            request["schema"], "final_map_author_citation_0001", allow_completed=True)
        self.assertEqual(plan["task_sha256"], context["task_sha256"])
        self.assertEqual(CONTINUATION._sha(plan_raw), request["plan_sha256"])

    def test_captured106_native_schema_failure_is_retained_as_legacy_history(self):
        """The rejected native schema attempt stays readable; current public success is tested on111."""
        fixture = Path("/private/tmp/atlas-final-map-assembly-20261015/prototype5-proof/frozen-original106-schema-failure")
        if not (fixture / "events/000106.json").is_file():
            self.skipTest("Immutable captured106 schema-failure fixture unavailable")
        events = CONTINUATION._events(fixture)
        worker = fixture / "workers/final_map_author_citation_0001"
        self.assertTrue((worker / "schema.json").is_file())
        self.assertTrue((worker / "cli-schema.json").is_file())
        self.assertTrue((worker / "stderr.txt").is_file())
        request, _ = CONTINUATION._read_json(fixture / "inputs/final-map-author-citation-0001.json", "historical request")
        self.assertNotIn("attempt", request)
        self.assertEqual(events[-1]["type"], "final_map_citation_revision_prepared")
        self.assertEqual(events[-1]["payload"].get("provider_dispatched"), False)
        self.assertEqual(events[-1]["payload"]["request_sha256"],
                         CONTINUATION._sha((fixture / "inputs/final-map-author-citation-0001.json").read_bytes()))

    def test_citation_correction_changes_only_existing_findings_refs(self):
        base = {"schema_version": 1, "task_sha256": "a" * 64, "source_identity_sha256": "b" * 64,
            "plan_sha256": "c" * 64, "history_tip_sha256": "d" * 64, "title": "Map",
            "explanation": "Same explanation preserved without edits.",
            "findings": [{"finding_id": "one", "statement": "A supported statement long enough.",
                "evidence_refs": ["e1"]}],
            "obligations": [{"obligation_id": "o1", "finding_ids": ["one"], "uncertainties": []}]}
        corrected = json.loads(json.dumps(base))
        corrected["findings"][0]["evidence_refs"].append("e2")
        self.assertTrue(CONTINUATION._final_map_citation_only_change(base, corrected, ["e1", "e2"]))
        for mutate in (
            lambda row: None,
            lambda row: row["findings"][0].update(statement="Edited statement that should be protected."),
            lambda row: row.update(explanation="A new explanation that is not permitted."),
            lambda row: row["findings"][0].update(evidence_refs=["e2"]),
            lambda row: row["findings"][0]["evidence_refs"].append("unknown"),
            lambda row: row["findings"][0].update(finding_id="renamed"),
            lambda row: row["obligations"][0]["finding_ids"].append("another-finding"),
            lambda row: row["obligations"][0].update(uncertainties=["Changed uncertainty text."]),
            lambda row: row["findings"].append({"finding_id": "new", "statement": "New statement long enough.", "evidence_refs": ["e2"]}),
        ):
            candidate = json.loads(json.dumps(base))
            mutate(candidate)
            self.assertFalse(CONTINUATION._final_map_citation_only_change(base, candidate, ["e1", "e2"]))
        schema = CONTINUATION._final_map_citation_schema(
            {"task_sha256": base["task_sha256"], "source_identity_sha256": base["source_identity_sha256"]},
            {"obligations": [{"obligation_id": "o1"}]}, base, ["e1", "e2"])
        self.assertEqual(schema["properties"]["title"], {"const": "Map"})
        self.assertEqual(schema["properties"]["explanation"], {"const": base["explanation"]})
        standard_obligations = CONTINUATION._final_map_schema(
            {"task_sha256": base["task_sha256"], "source_identity_sha256": base["source_identity_sha256"]},
            {"obligations": [{"obligation_id": "o1"}]}, ["e1", "e2"])["properties"]["obligations"]
        self.assertEqual(schema["properties"]["obligations"], standard_obligations)
        converted = CONTINUATION.route_autorun._cli_schema(schema)
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
        Draft202012Validator.check_schema(converted)
        self.assertEqual(schema["properties"]["obligations"]["type"], "array")
        self.assertNotIn("enum", schema["properties"]["obligations"])
        plan = {"follow_up_work": [{"follow_up_id": "assemble_reusable_map", "execution_state": "deferred"}]}
        rejected = [{"type": "final_map_revision_0002_review_completed", "payload": {"decision": "rejected"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(rejected, {}, plan), "final_map_citation_additions_prepare")
        citation = rejected + [{"type": "final_map_citation_revision_prepared"}]
        self.assertEqual(CONTINUATION._final_map_next_type(citation, {}, plan), "final_map_author_citation_0001")
        citation += [{"type": "final_map_citation_author_validated"}]
        self.assertEqual(CONTINUATION._final_map_next_type(citation, {}, plan), "final_map_citation_review_prepare")
        citation += [{"type": "final_map_citation_review_input_prepared"}]
        self.assertEqual(CONTINUATION._final_map_next_type(citation, {}, plan), "final_map_review_citation_0001")
        citation += [{"type": "final_map_citation_review_completed", "payload": {"decision": "rejected"}}]
        self.assertEqual(CONTINUATION._final_map_next_type(citation, {}, plan), "final_map_rejected")
        self.assertEqual(CONTINUATION._final_map_next_type(citation, {}, plan), "final_map_rejected")
    def test_revision_review_binds_current_receipt_on_captured84_preparation(self):
        """A captured rejected-84 state binds Sol's request to the corrected draft receipt."""
        captured = Path(os.environ.get("ATLAS_FINAL_MAP_FEEDBACK_CAPTURE",
            "/private/tmp/atlas-final-map-assembly-20261015/candidate-result/prototype3-frozen-final-84-copy"))
        if not (captured / "events/000086.json").is_file():
            self.skipTest("Prepared captured-84 feedback checkpoint unavailable")
        root = self.root / "captured84-review-binding"
        shutil.copytree(captured, root)
        old_paths = ("outputs/final-map.json", "outputs/final-map-review.json",
                     "inputs/final-map-author.json", "inputs/final-map-review.json")
        old_hashes = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in old_paths}
        plan, _plan_raw = CONTINUATION._read_json(root / "outputs/plan_author.json", "captured accepted plan")
        context = {"task_sha256": plan["task_sha256"], "source_identity_sha256": plan["source_identity_sha256"],
            "task_text": Path("/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt").read_text()}
        author_request, _ = CONTINUATION._read_json(root / "inputs/final-map-author-revision-0001.json", "captured correction request")
        evidence_id = author_request["evidence_ids"][0]
        draft = {"schema_version": 1, "task_sha256": author_request["task_sha256"],
            "source_identity_sha256": author_request["source_identity_sha256"], "plan_sha256": author_request["plan_sha256"],
            "history_tip_sha256": author_request["history_tip_sha256"], "title": "Synthetic captured-state map",
            "explanation": "Synthetic validation text only; this map exercises exact preservation receipt identity and makes no factual claims about the captured purchase flow.",
            "findings": [{"finding_id": "captured-test-finding", "statement": "Synthetic citation used only to exercise exact review request binding.",
                "evidence_refs": [evidence_id]}],
            "obligations": [{"obligation_id": item, "finding_ids": ["captured-test-finding"],
                "uncertainties": ["Synthetic fixture leaves factual adequacy unresolved."]}
                for item in author_request["obligation_ids"]]}
        draft_raw = CONTINUATION._json_bytes(draft)
        explanation_raw = draft["explanation"].encode("utf-8")
        draft_ref = CONTINUATION._artifact(root, "outputs/final-map-revision-0001.json", draft_raw)
        explanation_ref = CONTINUATION._artifact(root, "outputs/final-map-revision-0001.txt", explanation_raw)
        CONTINUATION._append(root, "final_map_revision_author_validated",
            {"map_sha256": hashlib.sha256(draft_raw).hexdigest()}, [draft_ref, explanation_ref])
        CONTINUATION._prepare_final_map_review(root, context, plan, CONTINUATION._events(root))
        events = CONTINUATION._events(root)
        review_request, _ = CONTINUATION._read_json(root / "inputs/final-map-review-revision-0001.json", "corrected review request")
        current_path = root / "outputs/final-map-preservation-review-revision-0001.json"
        historical_path = root / "outputs/final-map-preservation-revision-0001.json"
        current, current_raw = CONTINUATION._read_json(current_path, "current corrected-map receipt")
        historical_raw = historical_path.read_bytes()
        current_sha = hashlib.sha256(current_raw).hexdigest()
        historical_sha = hashlib.sha256(historical_raw).hexdigest()
        self.assertNotEqual(current_sha, historical_sha)
        revision_event = next(event for event in events if event.get("type") == "final_map_feedback_revision_prepared")
        self.assertEqual(revision_event["payload"]["preservation_receipt_sha256"], historical_sha)
        self.assertEqual(review_request["preservation_receipt_sha256"], current_sha)
        self.assertEqual(review_request["map_sha256"], hashlib.sha256(draft_raw).hexdigest())
        self.assertIn(json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2), review_request["prompt"])
        self.assertIn(f"exact map SHA-256 is {hashlib.sha256(draft_raw).hexdigest()}", review_request["prompt"])
        prepared = next(event for event in events if event.get("type") == "final_map_revision_review_input_prepared")
        self.assertEqual(prepared["payload"]["preservation_receipt_sha256"], current_sha)
        self.assertTrue(any(ref == {"path": current_path.relative_to(root).as_posix(), "sha256": current_sha,
            "bytes": len(current_raw)} for ref in prepared["artifacts"]))
        self.assertEqual(CONTINUATION._final_map_request_binding(root, context, "sol_review",
            review_request["prompt"], review_request["schema"], "final_map_review_revision_0001")[0], review_request)
        self.assertEqual(old_hashes, {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in old_paths})


if __name__ == "__main__":
    unittest.main()
# Plain-task intake prototype checks use the captured task and real read-only Atlas case.
import pytest as _pytest

_INTAKE_CASE_ROOT = Path(os.environ.get("ATLAS_INTAKE_CASE_DIR", "/private/tmp/atlas-discount-lifecycle-task-20261012"))
_INTAKE_TASK = _INTAKE_CASE_ROOT / "task.txt"
_INTAKE_ENVELOPE_PATH = _INTAKE_CASE_ROOT / "envelope.json"
try:
    _INTAKE_ENVELOPE = json.loads(_INTAKE_ENVELOPE_PATH.read_text(encoding="utf-8")) if _INTAKE_ENVELOPE_PATH.is_file() else {}
except (OSError, UnicodeDecodeError, json.JSONDecodeError):
    _INTAKE_ENVELOPE = {}
_INTAKE_READ_ONLY = _INTAKE_ENVELOPE.get("read_only", []) if isinstance(_INTAKE_ENVELOPE, dict) else []
_INTAKE_REPO = os.environ.get("ATLAS_INTAKE_REPO") or next((path for path in _INTAKE_READ_ONLY if path.endswith("taggable-api")), None)
_INTAKE_DB = os.environ.get("ATLAS_INTAKE_DB") or next((path for path in _INTAKE_READ_ONLY if path.endswith("atlas.sqlite")), None)
_INTAKE_CASE_AVAILABLE = _INTAKE_TASK.is_file() and bool(_INTAKE_REPO) and bool(_INTAKE_DB)
_INTAKE_SCRIPTS = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts"
sys.path.insert(0, os.fspath(_INTAKE_SCRIPTS))
import task_intake as _task_intake


def _intake_cli(*args):
    return subprocess.run([sys.executable, os.fspath(_INTAKE_SCRIPTS / "task_intake.py"), *args],
                          text=True, capture_output=True, check=False)


def _frozen_intake_start(run_dir, repo=_INTAKE_REPO, db=_INTAKE_DB):
    task_bytes = _INTAKE_TASK.read_bytes()
    identity = _task_intake._source_identity(repo, db)
    _task_intake._bind_or_start(run_dir, task_bytes, identity, _task_intake.DEFAULT_MAX_BYTES, create=True)


def _intake_tree_bytes(run_dir):
    return {path.relative_to(run_dir).as_posix(): path.read_bytes()
            for path in run_dir.rglob("*") if path.is_file()}


def _assert_real_intake_discovery(document):
    assert document["status"] == "awaiting-scope-review"
    assert document["semantic_scope_state"] == "unselected"
    assert document["task_sha256"] == hashlib.sha256(_INTAKE_TASK.read_bytes()).hexdigest()
    discovery = document["discovery"]
    candidates = discovery["candidates"]
    assert candidates
    selection = discovery["candidate_selection"]
    assert selection["included_candidates"] == len(candidates)
    assert selection["total_candidates"] == len(candidates) + selection["omitted_candidates"]
    assert len({candidate["controller_type_id"] for candidate in candidates}) > 1
    for candidate in candidates:
        assert candidate["fact_id"]
        assert candidate["action_source"]["fact_id"] == candidate["fact_id"]
        assert candidate["action_source"]["span"]
        assert candidate["controller_source"]["fact_id"]
        assert candidate["controller_source"]["span"]


@_pytest.mark.skipif(not _INTAKE_CASE_AVAILABLE, reason="captured Atlas read-only case is unavailable")
def test_plain_task_intake_preserves_stale_source_refusal_and_captured_discovery(tmp_path):
    """Current source identity stays fail-closed; discovery assertions use its saved capture."""
    run_dir = tmp_path / "intake-resume-case"
    _frozen_intake_start(run_dir)
    before = _intake_tree_bytes(run_dir)
    resumed = _intake_cli("resume", "--repo", _INTAKE_REPO, "--db", _INTAKE_DB,
                          "--task-file", os.fspath(_INTAKE_TASK), "--run-dir", os.fspath(run_dir))
    assert resumed.returncode == 3
    refused = json.loads(resumed.stdout)
    assert refused["status"] == "refused"
    assert refused["discovery"]["result"] == "refused"
    assert refused["discovery"]["reason"] == "no_saved_snapshot_matches_current_extractor_and_checkout"
    assert any("AGENTS.md" in mismatch.get("changed_paths", [])
               for mismatch in refused["discovery"]["source_mismatches"])
    after = _intake_tree_bytes(run_dir)
    assert all(after.get(path) == value for path, value in before.items())
    events = [json.loads(path.read_bytes()) for path in sorted((run_dir / "events").glob("*.json"))]
    assert len(events) == 2
    assert events[-1]["type"] == "discovery_completed"
    assert events[-1]["payload"]["discovery"]["result"] == "refused"
    captured = Path("/private/tmp/atlas-discount-lifecycle-task-20261012/operator-captures-v2/manifest/resume-stdout.json")
    assert captured.is_file()
    _assert_real_intake_discovery(json.loads(captured.read_text(encoding="utf-8")))


@_pytest.mark.skipif(not _INTAKE_CASE_AVAILABLE, reason="captured Atlas read-only case is unavailable")
def test_changed_task_bytes_are_refused_without_changing_frozen_intake(tmp_path):
    run_dir = tmp_path / "changed-input-case"
    _frozen_intake_start(run_dir)
    changed = tmp_path / "changed-task.txt"
    changed.write_bytes(_INTAKE_TASK.read_bytes() + b"\\n")
    before = {path.name: path.read_bytes() for path in (run_dir / "events").glob("*.json")} if (run_dir / "events").exists() else {
        path.name: path.read_bytes() for path in (run_dir / "task.txt", run_dir / "source-identity.json", run_dir / "manifest.json") if path.exists()
    }
    refused = _intake_cli("resume", "--repo", _INTAKE_REPO, "--db", _INTAKE_DB,
                          "--task-file", os.fspath(changed), "--run-dir", os.fspath(run_dir))
    assert refused.returncode == 2
    assert "task bytes differ" in refused.stderr
    if (run_dir / "events").exists():
        after = {path.name: path.read_bytes() for path in (run_dir / "events").glob("*.json")}
    else:
        after = {path.name: path.read_bytes() for path in (run_dir / "task.txt", run_dir / "source-identity.json", run_dir / "manifest.json") if path.exists()}
    assert after == before


@_pytest.mark.skipif(not _INTAKE_CASE_AVAILABLE, reason="captured Atlas read-only case is unavailable")
def test_changed_database_identity_is_refused_without_changing_frozen_intake(tmp_path):
    run_dir = tmp_path / "changed-database-case"
    database = tmp_path / "identity-only-database.sqlite"
    database.write_bytes(b"first database identity")
    _frozen_intake_start(run_dir, db=os.fspath(database))
    before = _intake_tree_bytes(run_dir)
    database.write_bytes(b"second database identity")
    refused = _intake_cli("resume", "--repo", _INTAKE_REPO, "--db", os.fspath(database),
                          "--task-file", os.fspath(_INTAKE_TASK), "--run-dir", os.fspath(run_dir))
    assert refused.returncode == 2
    assert "source identity changed" in refused.stderr
    assert _intake_tree_bytes(run_dir) == before


@_pytest.mark.skipif(not _INTAKE_CASE_AVAILABLE, reason="captured Atlas read-only case is unavailable")
def test_changed_repository_identity_is_refused_without_changing_frozen_intake(tmp_path):
    run_dir = tmp_path / "changed-repository-case"
    _frozen_intake_start(run_dir)
    alternate_repo = tmp_path / "other-checkout"
    alternate_repo.mkdir()
    subprocess.run(["git", "init", "--quiet", os.fspath(alternate_repo)], check=True)
    subprocess.run(["git", "-C", os.fspath(alternate_repo), "-c", "user.name=Intake Test",
                    "-c", "user.email=intake-test@example.invalid", "commit", "--quiet", "--allow-empty",
                    "-m", "baseline"], check=True)
    before = _intake_tree_bytes(run_dir)
    refused = _intake_cli("resume", "--repo", os.fspath(alternate_repo), "--db", _INTAKE_DB,
                          "--task-file", os.fspath(_INTAKE_TASK), "--run-dir", os.fspath(run_dir))
    assert refused.returncode == 2
    assert "source identity changed" in refused.stderr
    assert _intake_tree_bytes(run_dir) == before


@_pytest.mark.skipif(not _INTAKE_CASE_AVAILABLE, reason="captured Atlas read-only case is unavailable")
def test_changed_discovery_byte_budget_is_refused_without_changing_frozen_intake(tmp_path):
    run_dir = tmp_path / "changed-budget-case"
    _frozen_intake_start(run_dir)
    before = _intake_tree_bytes(run_dir)
    refused = _intake_cli("resume", "--repo", _INTAKE_REPO, "--db", _INTAKE_DB,
                          "--task-file", os.fspath(_INTAKE_TASK), "--run-dir", os.fspath(run_dir),
                          "--max-bytes", "100")
    assert refused.returncode == 2
    assert "byte budget differs" in refused.stderr
    assert _intake_tree_bytes(run_dir) == before


def test_accepted_fit_actor_rebind_authenticates_live_inputs_before_writing(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/task_continuation.py"
    scripts = str(source.parent)
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location("accepted_fit_rebind_order_test", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    manifest = tmp_path / "engine-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    prior = {"path": "/saved/actor.py", "sha256": "a" * 64, "bytes": 10}
    source_event = {"type": "continuation_executor_resumed", "event_sha256": "b" * 64,
                    "payload": {"adoption_kind": "accepted_task_fit_worker", "executor": prior}}
    events = [source_event]
    loaded = []
    writes = []

    def reject_live_inputs(root, repo, db, task_file, intake_run):
        loaded.append((repo, db, task_file, intake_run))
        raise module.ContinuationError("requested task differs from the exact immutable intake task")

    monkeypatch.setattr(module, "_load_verified_engine", lambda _root: None)
    monkeypatch.setattr(module, "_verify_engine_transition", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(module, "_load", reject_live_inputs)
    monkeypatch.setattr(module, "_executor_record", lambda: {"path": "/new/actor.py", "sha256": "c" * 64, "bytes": 10})
    monkeypatch.setattr(module, "_next_task_fit_actor_archive", lambda *_args: writes.append("archive-path") or "inputs/engine-transition/resumed-executor-0001.py")
    monkeypatch.setattr(module, "_artifact", lambda *_args: writes.append("artifact"))
    monkeypatch.setattr(module, "_append", lambda *_args: writes.append("event"))

    with unittest.TestCase().assertRaisesRegex(module.ContinuationError, "requested task differs"):
        module._adopt_latest_accepted_fit_actor(
            "/live/repo", "/live/db.sqlite", "/live/task.txt", "/live/intake",
            os.fspath(tmp_path), os.fspath(manifest), b"manifest", tmp_path, events)

    assert loaded == [("/live/repo", "/live/db.sqlite", "/live/task.txt", "/live/intake")]
    assert writes == []


@_pytest.mark.skipif(not (_INTAKE_CASE_AVAILABLE and Path(
    "/private/tmp/atlas-next-investigation-task-20261013/remaining-drive-20261014/worker100-retry-correction/cases/event65-final/events/000065.json"
).is_file()), reason="captured event65 source-bound checkpoint is unavailable")
def test_event65_public_adoption_refuses_changed_caller_before_actor_write(tmp_path):
    import shutil

    source = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/task_continuation.py"
    prefix = Path("/private/tmp/atlas-next-investigation-task-20261013/remaining-drive-20261014/worker100-retry-correction/cases/event65-final")
    run_dir = tmp_path / "event65-run"
    shutil.copytree(prefix, run_dir)
    changed_task = tmp_path / "changed-task.txt"
    task_bytes = _INTAKE_TASK.read_bytes()
    changed_task.write_bytes(bytes([task_bytes[0] ^ 1]) + task_bytes[1:])
    before = _intake_tree_bytes(run_dir)
    before_dirs = sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*") if path.is_dir())
    command = [sys.executable, os.fspath(source), "resume", "--repo", _INTAKE_REPO,
               "--db", _INTAKE_DB, "--task-file", os.fspath(changed_task),
               "--intake-run", "/private/tmp/atlas-discount-lifecycle-task-20261012/run",
               "--run-dir", os.fspath(run_dir), "--engine-manifest",
               "/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json",
               "--max-worker-calls", "1", "--timeout-seconds", "180", "--prepare-only",
               "--adopt-checkpoint-executor"]
    result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=180,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    after = _intake_tree_bytes(run_dir)
    after_dirs = sorted(path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*") if path.is_dir())
    assert result.returncode == 2
    assert "requested task differs from the exact immutable intake task" in result.stderr
    assert before == after
    assert before_dirs == after_dirs
    assert len(list((run_dir / "events").glob("*.json"))) == 65


@_pytest.mark.skipif(not _INTAKE_CASE_AVAILABLE, reason="captured Atlas read-only case is unavailable")
def test_development_probe_operator_failure_preserves_original_error_and_correction(tmp_path):
    variant = tmp_path / "variant.json"
    variant.write_text(json.dumps({"configuration": {"case_id": "approved-plain-task"}}), encoding="utf-8")
    result_path = tmp_path / "result.json"
    telemetry_path = tmp_path / "telemetry.jsonl"
    env = os.environ.copy()
    env.update({"EXPERIMENT_WORK_DIR": os.fspath(tmp_path),
                "EXPERIMENT_INPUT_PATH": os.fspath(_INTAKE_TASK),
                "EXPERIMENT_RESULT_PATH": os.fspath(result_path),
                "EXPERIMENT_TELEMETRY_PATH": os.fspath(telemetry_path),
                "EXPERIMENT_VARIANT_PATH": os.fspath(variant),
                "EXPERIMENT_VARIANT_ID": "operator-failure-proof",
                "ATLAS_INTAKE_INJECT_OPERATOR_FAILURE": "1"})
    failed = subprocess.run([sys.executable, os.fspath(Path(__file__).resolve()),
                             "--atlas-native-intake-experiment"], env=env,
                            text=True, capture_output=True, check=False)
    assert failed.returncode != 0
    assert "RuntimeError: injected operator failure proof" in failed.stderr
    records = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["event"] == "operator_error"
    assert "RuntimeError: injected operator failure proof" in records[0]["message"]
    assert records[0]["correction"]
    assert not result_path.exists()


@_pytest.mark.skipif(not Path("/private/tmp/atlas-next-investigation-task-20261013/frozen-rejected-next-unit-v7-24").is_dir(),
                    reason="captured rejected next-route checkpoint unavailable")
def test_public_feedback_stale_source_refusal_preserves_saved_rejection_and_prefix(tmp_path):
    """Preserve the historical rejection contract and refuse stale live identity without writes."""
    admin = Path("/private/tmp/atlas-next-investigation-task-20261013")
    frozen = admin / "frozen-rejected-next-unit-v7-24"
    register_path = admin / "accepted-first-unit-register.json"
    if not register_path.is_file():
        _pytest.skip("accepted-prefix register unavailable")
    register = json.loads(register_path.read_bytes())
    run = tmp_path / "same-task-feedback"
    shutil.copytree(frozen, run)
    review_path = run / "outputs/map_review_c8015930ced6b2dd8402e4be_combined.json"
    validation_path = run / "outputs/map_review_c8015930ced6b2dd8402e4be_validation.json"
    review = json.loads(review_path.read_bytes())
    validation = json.loads(validation_path.read_bytes())
    events = [json.loads(path.read_bytes()) for path in sorted((run / "events").glob("*.json"))]
    rejection = events[-1]
    assert rejection["type"] == "route_mapping_review_validated"
    assert rejection["payload"]["validation_result"] == validation["result"] == "rejected"
    assert review["task_fit"]["decision"] == "accepted"
    protected = {row["path"]: row["sha256"] for row in register["files"]}
    before = {p.relative_to(run).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in run.rglob("*") if p.is_file()}
    command = [sys.executable, "-B", os.fspath(Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/task_continuation.py"),
        "resume", "--repo", _INTAKE_REPO, "--db", _INTAKE_DB,
        "--task-file", "/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt",
        "--intake-run", "/private/tmp/atlas-discount-lifecycle-task-20261012/run", "--run-dir", os.fspath(run),
        "--engine-manifest", "/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json",
        "--max-worker-calls", "1", "--timeout-seconds", "180", "--prepare-only", "--adopt-feedback-executor"]
    refused = subprocess.run(command, text=True, capture_output=True, check=False, timeout=180,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert refused.returncode == 2
    assert "source" in refused.stderr.lower()
    after = {p.relative_to(run).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in run.rglob("*") if p.is_file()}
    assert after == before
    assert all(hashlib.sha256((run / rel).read_bytes()).hexdigest() == digest for rel, digest in protected.items())


@_pytest.mark.skipif(not Path("/private/tmp/atlas-next-investigation-task-20261013/frozen-rejected-next-unit-v7-24").is_dir(),
                    reason="captured rejected next-route checkpoint unavailable")
def test_public_feedback_transition_refuses_changed_saved_review_before_writes(tmp_path):
    import shutil
    admin = Path("/private/tmp/atlas-next-investigation-task-20261013")
    run = tmp_path / "tampered-feedback-source"
    shutil.copytree(admin / "frozen-rejected-next-unit-v7-24", run)
    source = Path(__file__).resolve().parents[1] / "skills/codebase-atlas-machinery/scripts/task_continuation.py"
    changed = run / "outputs/map_review_c8015930ced6b2dd8402e4be_combined.json"
    changed.write_bytes(changed.read_bytes() + b" ")
    before = {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in run.rglob("*") if p.is_file()}
    command = [sys.executable, "-B", os.fspath(source), "resume", "--repo", _INTAKE_REPO,
               "--db", _INTAKE_DB, "--task-file", "/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt",
               "--intake-run", "/private/tmp/atlas-discount-lifecycle-task-20261012/run",
               "--run-dir", os.fspath(run), "--engine-manifest",
               "/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json",
               "--max-worker-calls", "1", "--timeout-seconds", "180", "--prepare-only",
               "--adopt-feedback-executor"]
    refused = subprocess.run(command, text=True, capture_output=True, check=False)
    assert refused.returncode == 2
    assert "a committed continuation artifact changed" in refused.stderr
    after = {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in run.rglob("*") if p.is_file()}
    assert after == before
    assert len(list((run / "events").glob("*.json"))) == 24
    assert not (run / "inputs/engine-transition/route-feedback-executor.py").exists()

# Opt-in worker76 adapter; public task-continuation CLI runs from this bundle-local tree.
if __name__ == "atlas_next_dp_adapter" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "--atlas-dp-worker76":
    import hashlib as _h, json as _j, os as _o, shutil as _sh, signal as _sig, subprocess as _sp, sys as _s, time as _t
    from pathlib import Path as _P
    _work=_P(_o.environ["EXPERIMENT_WORK_DIR"]).resolve(); _inp=_P(_o.environ["EXPERIMENT_INPUT_PATH"]).resolve(strict=True)
    _out=_P(_o.environ["EXPERIMENT_RESULT_PATH"]); _tel=_P(_o.environ["EXPERIMENT_TELEMETRY_PATH"]); _variant=_o.environ["EXPERIMENT_VARIANT_ID"]
    _sha=lambda b:_h.sha256(b).hexdigest()
    _idxpath=_P(__file__).resolve().parents[2]/"capture-index-v1.json"
    if not _idxpath.is_file(): _idxpath=_P("/private/tmp/atlas-next-investigation-task-20261013/probes/development-probe-next-v7/capture-index-v1.json")
    _idxraw=_idxpath.read_bytes();
    if _sha(_idxraw)!="256e1007b8ebf851a019dba4077f3b62ce0b2df6ce1f620f54fe335cb78fc64a": raise SystemExit("frozen capture index digest changed")
    _idx=_j.loads(_idxraw); _inputsha=_sha(_inp.read_bytes())
    _case=next((k for k,v in _idx["case_sha256"].items() if v==_inputsha),None)
    if _case is None: raise SystemExit("case input hash is outside the frozen four-case set")
    # Composition omits EXPERIMENT_VARIANT_PATH; bind optional configuration when present.
    _cfgpath=_o.environ.get("EXPERIMENT_VARIANT_PATH"); _cfg=_j.loads(_P(_cfgpath).read_bytes()).get("configuration",{}) if _cfgpath else {}
    if _cfg.get("case_id") not in (None,_case): raise SystemExit("variant case id differs from frozen input")
    _srcroot=_P(__file__).resolve().parents[1]; _script=_srcroot/"skills/codebase-atlas-machinery/scripts/task_continuation.py"
    _module_sha=_sha(_script.read_bytes()); _approach="local-v11-legacy-control" if _module_sha==_idx["control_sha256"] else "local-v11-candidate" if _module_sha==_idx["candidate_sha256"] else None
    if _approach is None: raise SystemExit("bundle-local executor SHA is not an admitted local variant")
    _fx=_idx["fixtures"][_case]; _fixture=_P(_fx["path"]).resolve(strict=True)
    def _tree(r): return {str(p.relative_to(r)):_sha(p.read_bytes()) for p in r.rglob("*") if p.is_file()}
    _ftree=_tree(_fixture)
    if _sha(_j.dumps(_ftree,sort_keys=True,separators=(",",":")).encode())!=_fx["tree_sha256"]: raise SystemExit("frozen case-state tree changed")
    _run=_work/"local-public-run"; _sh.copytree(_fixture,_run)
    _repo=_idx["repo"]; _db=_idx["db"]; _task=_fx.get("task_file",_idx["task_file"]); _intake=_fx.get("intake_run",_idx["intake_run"]); _engine=_idx["engine_manifest"]
    _protected={rel:digest for rel,digest in _ftree.items() if rel.startswith("events/") or rel in _fx.get("protected_files",[])}
    def _base(cmd="resume"):
        a=[_s.executable,"-B",str(_script),cmd,"--repo",_repo,"--db",_db,"--task-file",_task,"--intake-run",_intake,"--run-dir",str(_run),"--engine-manifest",_engine]
        if cmd=="resume": a.extend(["--max-worker-calls","1","--timeout-seconds","180"])
        return a
    def _call(argv,timeout=200):
        p=_sp.run(argv,text=True,capture_output=True,check=False,timeout=timeout,env={**_o.environ,"PYTHONDONTWRITEBYTECODE":"1"})
        try: body=_j.loads(p.stdout)
        except Exception:
            try: body=_j.loads(p.stderr)
            except Exception: body=None
        return {"argv":argv,"returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"body":body}
    def _events():
        out=[]
        for p in sorted((_run/"events").glob("*.json")):
            try: out.append((_j.loads(p.read_text()),p))
            except Exception: pass
        return out
    def _worker_inventory():
        return {k:v for k,v in _tree(_run).items() if k.startswith("workers/") and ("completion-register" in k or k.endswith(("/answer.txt","/events.jsonl","/prompt.txt","/argv.json")))}
    def _public(cmd,extra=()): return _call(_base(cmd)+list(extra))
    try:
        _raw={"case_id":_case,"case_input_sha256":_inputsha,"approach_id":_approach,"candidate_module_sha256":_module_sha,"executor":{"path":str(_script),"sha256":_module_sha,"bytes":_script.stat().st_size},"capture_index_sha256":_sha(_idxraw),"fixture_tree_sha256":_fx["tree_sha256"],"canonical_publication":False}
        _pre_events=len(_events()); _workers_before=_worker_inventory(); _new_cmds=[]
        if _case=="saved-task-integrity":
            _before=_tree(_run); _taskpath=_P(_task).resolve(strict=True); _intakepath=_P(_intake).resolve(strict=True)
            def _external(): return {str(p.relative_to(_intakepath)):_sha(p.read_bytes()) for p in _intakepath.rglob("*") if p.is_file()}
            _external_before=_external(); _task_before=_sha(_taskpath.read_bytes()); _task_bytes=len(_taskpath.read_bytes())
            _capture_bound=(_fx["events"]==16 and len(list((_run/"events").glob("*.json")))==16 and _task_before==_fx["expected_corrupt_task_sha256"] and _task_bytes==_fx["expected_corrupt_task_bytes"] and _sha(_P(_idx["task_file"]).read_bytes())==_idx["case_sha256"]["original-task"])
            _raw["integrity_refusal"]=_public("resume",["--adopt-accepted-executor","--prepare-only"]); _new_cmds.append(_raw["integrity_refusal"])
            _external_after=_external(); _task_after=_sha(_taskpath.read_bytes()); _run_after=_tree(_run)
            _body=_raw["integrity_refusal"].get("body") or {}; _raw["integrity_refusal"].update({"constructed_mutation":_capture_bound,"captured_child_events":len(list((_run/"events").glob("*.json"))),"task_sha256_before":_task_before,"task_sha256_after":_task_after,"task_bytes_before":_task_bytes,"task_bytes_after":len(_taskpath.read_bytes()),"external_intake_before":_external_before,"external_intake_after":_external_after,"state_unchanged":_run_after==_before and _external_after==_external_before and _task_after==_task_before,"writes_before_refusal":int(_run_after!=_before or _external_after!=_external_before or _task_after!=_task_before),"expected_refusal_body":_body.get("error")=="bound task artifact length or hash is invalid","expected_returncode":_raw["integrity_refusal"].get("returncode")==2})
        elif _case=="accepted-unit-no-advance":
            _flag="--adopt-accepted-executor" if _fx["events"]==16 else "--adopt-checkpoint-executor"
            _raw["public_command"]=_public("resume",[_flag,"--prepare-only"]); _new_cmds.append(_raw["public_command"])
        elif _case=="interrupted-next-work" and _approach=="local-v11-candidate":
            _raw["adoption"]=_public("resume",["--adopt-checkpoint-executor","--prepare-only"]); _new_cmds.append(_raw["adoption"])
            _cmd=_base("resume"); _proc=_sp.Popen(_cmd,text=True,stdout=_sp.PIPE,stderr=_sp.PIPE,env={**_o.environ,"PYTHONDONTWRITEBYTECODE":"1"})
            _accepted=_run/"events/000035.json"; _until=_t.monotonic()+100; _seen=False
            while _t.monotonic()<_until:
                if _accepted.is_file():
                    _event=_j.loads(_accepted.read_bytes()); _payload=_event.get("payload",{})
                    if _event.get("type")=="route_mapping_review_accepted" and _payload.get("route_fact_id")=="c8015930ced6b2dd8402e4be" and _payload.get("source_review")=="accepted" and _payload.get("task_fit")=="accepted":
                        _seen=True; _proc.send_signal(_sig.SIGTERM); break
                if _proc.poll() is not None: break
                _t.sleep(.001)
            try: _stdout,_stderr=_proc.communicate(timeout=4)
            except _sp.TimeoutExpired: _proc.kill(); _stdout,_stderr=_proc.communicate()
            _raw["interruption"]={"argv":_cmd,"returncode":_proc.returncode,"stdout":_stdout,"stderr":_stderr,"sigterm_after_event35":_seen,"accepted_event_sha256":_sha(_accepted.read_bytes()) if _accepted.is_file() else None}
            # Resume the same interrupted public run in prepare-only mode, then repeat for idempotence.
            _raw["resume_prepare"]=_public("resume",["--prepare-only"]); _new_cmds.append(_raw["resume_prepare"])
            _after_resume=_tree(_run); _workers_after_resume=_worker_inventory(); _events_after_resume=len(_events())
            _raw["resume_prepare_tree_sha256"]=_sha(_j.dumps(_after_resume,sort_keys=True,separators=(",",":")).encode())
            _raw["resume_repeat"]=_public("resume",["--prepare-only"]); _new_cmds.append(_raw["resume_repeat"])
            _after_repeat=_tree(_run); _raw["resume_repeat_unchanged"]=_after_repeat==_after_resume; _raw["resume_repeat_events_unchanged"]=len(_events())==_events_after_resume; _raw["resume_repeat_workers_unchanged"]=_worker_inventory()==_workers_after_resume; _raw["resume_repeat_tree_sha256"]=_sha(_j.dumps(_after_repeat,sort_keys=True,separators=(",",":")).encode())
        else:
            if _fx["events"]>=31:
                _raw["adoption"]=_public("resume",["--adopt-checkpoint-executor","--prepare-only"]); _new_cmds.append(_raw["adoption"])
                if _approach=="local-v11-candidate": _raw["public_command"]=_public("resume"); _new_cmds.append(_raw["public_command"])
            else:
                _raw["public_command"]=_public("resume",["--adopt-accepted-executor","--prepare-only"]); _new_cmds.append(_raw["public_command"])
        _post=_tree(_run); _raw["protected_prefix_unchanged"]=all(_post.get(k)==v for k,v in _protected.items())
        _all_events=_events(); _new_events=_all_events[_pre_events:]; _raw["appended_events"]=[{"relative_path":p.relative_to(_run).as_posix(),"sha256":_sha(p.read_bytes()),"payload":ev} for ev,p in _new_events]
        _raw["event_types"]=[ev.get("type") for ev,p in _all_events]
        _raw["worker_inventory_before"]=_workers_before; _workers_after=_worker_inventory(); _raw["worker_inventory_after"]=_workers_after
        _raw["new_worker_files"]={k:v for k,v in _workers_after.items() if _workers_before.get(k)!=v}
        _raw["new_worker_completions"]=sum(1 for ev,p in _new_events if str(ev.get("type","")).endswith("_worker_completed"))
        _raw["provider_calls_observed"]=sum(1 for ev,p in _new_events if ev.get("payload",{}).get("provider_dispatched") is True)
        # Expose only review/validation artifacts whose hashes are named by newly appended event payloads.
        _refs={a.get("path"):a.get("sha256") for ev,p in _new_events for a in ev.get("artifacts",[]) if a.get("path")}
        _raw["event_artifact_hashes"]=_refs
        _raw["source_review"]={k:{"declared_sha256":v,"actual_sha256":_sha((_run/k).read_bytes()),"hash_matches":_sha((_run/k).read_bytes())==v,"value":_j.loads((_run/k).read_bytes())} for k,v in _refs.items() if "map_review" in k and "combined" in k and (_run/k).is_file()}
        _raw["task_fit_review"]=_raw["source_review"]
        _raw["new_validation"]={k:{"declared_sha256":v,"actual_sha256":_sha((_run/k).read_bytes()),"hash_matches":_sha((_run/k).read_bytes())==v,"value":_j.loads((_run/k).read_bytes())} for k,v in _refs.items() if "validation.json" in k and (_run/k).is_file()}
        _raw["new_semantic_acceptance"]=[ev for ev,p in _new_events if ev.get("type")=="mapping_review_accepted"]
        _successful=[c for c in _new_cmds if c.get("returncode")==0 and isinstance(c.get("body"),dict)]
        _raw["final_status"]=_successful[-1]["body"] if _successful else None
        _raw["task_complete"]=bool((_raw.get("final_status") or {}).get("task_complete"))
        _raw["canonical_publication"]=bool((_raw.get("final_status") or {}).get("canonical_publication"))
        _result={"schema_version":1,"variant_id":_variant,"status":"completed","outcome":{"raw":_raw},"metrics":{},"error":None}
        _out.parent.mkdir(parents=True,exist_ok=True); _out.write_text(_j.dumps(_result,sort_keys=True)+"\n")
        _tel.parent.mkdir(parents=True,exist_ok=True); _tel.write_text(_j.dumps({"schema_version":1,"sequence":1,"event":"work_completed","recorded_at":_t.strftime("%Y-%m-%dT%H:%M:%SZ",_t.gmtime()),"variant_id":_variant,"message":"Executed the local public continuation path on the bound captured case state.","evidence_sha256":_sha(_j.dumps(_raw,sort_keys=True).encode()),"observations":{"case_id":_case,"approach_id":_approach,"executor_sha256":_module_sha,"appended_event_count":len(_new_events),"provider_calls_observed":_raw["provider_calls_observed"],"new_worker_completions":_raw["new_worker_completions"]}},sort_keys=True)+"\n")
        print(_j.dumps(_result,sort_keys=True)); raise SystemExit(0)
    except Exception as _exc: raise SystemExit(f"worker76 local public adapter failed: {type(_exc).__name__}: {_exc}")
def test_historical_acceptance_validator_only_rejects_acceptance_before_handoff():
    """A later accepted citation-map finalization preserves the earlier actor handoff."""
    handoff = {"type": "continuation_executor_resumed", "sequence": 101,
               "payload": {"adoption_kind": "final_map_citation_accepted_review_finalize"}}
    accepted_after = {"type": "final_map_accepted", "sequence": 102}
    accepted_before = {"type": "final_map_accepted", "sequence": 100}
    assert not CONTINUATION._final_acceptance_precedes_handoff([handoff, accepted_after], handoff)
    assert CONTINUATION._final_acceptance_precedes_handoff([accepted_before, handoff], handoff)
    assert CONTINUATION._final_acceptance_precedes_handoff(
        [handoff, {"type": "final_map_accepted"}], {"type": "continuation_executor_resumed"})


def test_citation_finalize_handoff_history_survives_later_acceptance():
    """Synthetic consumer-boundary proof; native request/worker checks are patched, not claimed."""
    with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
        root = Path(temp)
        context = {"task_sha256": "a" * 64, "source_identity_sha256": "b" * 64}
        plan = {"obligations": []}
        plan_raw = json.dumps(plan, sort_keys=True).encode()
        base = {"schema_version": 1, "task_sha256": context["task_sha256"],
                "source_identity_sha256": context["source_identity_sha256"], "plan_sha256": "c" * 64,
                "history_tip_sha256": "d" * 64, "title": "Preserved", "explanation": "Preserved explanation.",
                "findings": [{"finding_id": "f1", "statement": "A fixed supported statement.",
                              "evidence_refs": ["e1"]}],
                "obligations": []}
        draft = json.loads(json.dumps(base))
        draft["findings"][0]["evidence_refs"].append("e2")
        review = {"decision": "accepted"}
        request = {"prompt": "synthetic", "schema": {}}
        author_request = {"synthetic": True}
        catalogue = {"evidence": [{"evidence_id": "e1"}, {"evidence_id": "e2"}],
                     "evidence_ids": ["e1", "e2"]}
        values = {
            "outputs/plan_author.json": plan,
            "inputs/final-map-review-citation-0001.json": request,
            "outputs/final-map-citation-0001.json": draft,
            "outputs/final-map-review-citation-0001.json": review,
            "outputs/final-map-revision-0002.json": base,
            "inputs/final-map-author-revision-0002.json": catalogue,
            "inputs/final-map-author-citation-0001.json": author_request,
        }
        raw = {}
        for rel, value in values.items():
            data = json.dumps(value, sort_keys=True).encode()
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            raw[rel] = data
        archive = "inputs/engine-transition/resumed-executor-0005.py"
        archive_bytes = b"synthetic installed executor bytes"
        (root / archive).parent.mkdir(parents=True, exist_ok=True)
        (root / archive).write_bytes(archive_bytes)
        prior = {"path": "/candidate/old.py", "sha256": "e" * 64, "bytes": 2}
        current = {"path": "/installed/task_continuation.py",
                   "sha256": hashlib.sha256(archive_bytes).hexdigest(), "bytes": len(archive_bytes)}
        source = {"type": "final_map_citation_review_completed", "sequence": 104,
                  "event_sha256": "f" * 64, "payload": {"decision": "accepted",
                  "map_sha256": hashlib.sha256(raw["outputs/final-map-citation-0001.json"]).hexdigest()}}
        author_event = {"type": "final_map_author_citation_0001_worker_completed",
                        "payload": {"worker_thread_id": "author-thread"}}
        review_worker = {"type": "final_map_review_citation_0001_worker_completed",
                         "payload": {"worker_thread_id": "review-thread", "answer_sha256": "1" * 64}}
        refs = {
            archive: current["sha256"],
            "outputs/final-map-revision-0002.json": hashlib.sha256(raw["outputs/final-map-revision-0002.json"]).hexdigest(),
            "outputs/final-map-citation-0001.json": hashlib.sha256(raw["outputs/final-map-citation-0001.json"]).hexdigest(),
            "outputs/final-map-review-citation-0001.json": hashlib.sha256(raw["outputs/final-map-review-citation-0001.json"]).hexdigest(),
            "inputs/final-map-review-citation-0001.json": hashlib.sha256(raw["inputs/final-map-review-citation-0001.json"]).hexdigest(),
        }
        handoff = {"type": "continuation_executor_resumed", "sequence": 105,
            "previous_event_sha256": source["event_sha256"], "artifacts": [{"path": k, "sha256": v} for k, v in refs.items()],
            "payload": {"source_event_sha256": source["event_sha256"],
                "previous_executor": prior, "executor": current, "actor_archive_path": archive,
                "adoption_kind": "final_map_citation_accepted_review_finalize",
                "source_phase": "final_map_review_citation_0001", "task_sha256": context["task_sha256"],
                "source_identity_sha256": context["source_identity_sha256"], "plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
                "map_sha256": refs["outputs/final-map-citation-0001.json"],
                "base_map_sha256": refs["outputs/final-map-revision-0002.json"],
                "review_sha256": refs["outputs/final-map-review-citation-0001.json"],
                "request_sha256": refs["inputs/final-map-review-citation-0001.json"],
                "response_sha256": review_worker["payload"]["answer_sha256"]}}
        accepted_after = {"type": "final_map_accepted", "sequence": 106}
        events = [source, author_event, review_worker, handoff, accepted_after]
        def read_json(path, _label):
            rel = Path(path).relative_to(root).as_posix()
            return values[rel], raw[rel]
        with mock.patch.object(CONTINUATION, "_read_json", side_effect=read_json), \
             mock.patch.object(CONTINUATION, "_final_map_request_binding"), \
             mock.patch.object(CONTINUATION, "_verify_final_map_worker"), \
            mock.patch.object(CONTINUATION, "_validate_final_map"), \
            mock.patch.object(CONTINUATION, "_validate_final_map_review"):
            assert CONTINUATION._verify_task_fit_actor_handoffs(
                root, events, context, plan_raw, prior, [handoff], current_executor=current)
            before_unadmitted = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in root.rglob("*") if p.is_file()}
            unadmitted = {"path": "/unadmitted/task_continuation.py", "sha256": "9" * 64, "bytes": 21}
            assert not CONTINUATION._verify_task_fit_actor_handoffs(
                root, events, context, plan_raw, prior, [handoff], current_executor=unadmitted)
            assert before_unadmitted == {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in root.rglob("*") if p.is_file()}
            bad_binding = json.loads(json.dumps(handoff))
            bad_binding["payload"]["request_sha256"] = "0" * 64
            assert not CONTINUATION._verify_task_fit_actor_handoffs(
                root, [source, author_event, review_worker, bad_binding, accepted_after],
                context, plan_raw, prior, [bad_binding], current_executor=current)
            accepted_before = {"type": "final_map_accepted", "sequence": 103}
            assert not CONTINUATION._verify_task_fit_actor_handoffs(
                root, [accepted_before, source, author_event, review_worker, handoff, accepted_after],
                context, plan_raw, prior, [handoff], current_executor=current)


def test_historical_citation_finalizer_reads_the_legacy_artifact_family():
    """An accepted attempt-less historical review stays on its immutable legacy paths."""
    assert CONTINUATION._final_map_citation_artifact_paths(None) == (
        "outputs/final-map-citation-0001.json", "outputs/final-map-citation-0001.txt",
        "inputs/final-map-review-citation-0001.json", "outputs/final-map-review-citation-0001.json")
    assert CONTINUATION._final_map_citation_artifact_paths(2) == CONTINUATION._citation_additions_paths(2)
    with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
        root = Path(temp)
        plan = {"obligations": []}
        context = {"task_sha256": "a" * 64, "source_identity_sha256": "b" * 64}
        review_event = {"type": "final_map_citation_review_completed", "sequence": 2,
            "event_sha256": "c" * 64, "payload": {"decision": "accepted",
                "review_phase": "final_map_review_citation_0001"}}
        prepared = {"type": "final_map_citation_review_input_prepared", "sequence": 1,
                    "payload": {}}
        values = {
            "outputs/plan_author.json": plan,
            "outputs/final-map-citation-0001.json": {"history_tip_sha256": "d" * 64},
            "inputs/final-map-review-citation-0001.json": {"history_tip_sha256": "d" * 64},
        }
        for rel, value in values.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(json.dumps(value, sort_keys=True).encode())
        for rel, raw in (("outputs/final-map-citation-0001.txt", b"saved legacy explanation"),
                         ("outputs/final-map-review-citation-0001.json", b"{}")):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        expected = {"outputs/final-map-citation-0001.json", "outputs/final-map-citation-0001.txt",
                    "outputs/final-map-review-citation-0001.json", "inputs/final-map-review-citation-0001.json"}
        plan_path = root / "outputs/plan_author.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_raw = json.dumps(plan, sort_keys=True).encode()
        plan_path.write_bytes(plan_raw)
        reads = []
        def read_until_selected(path, label):
            relative = Path(path).relative_to(root).as_posix()
            reads.append(relative)
            if relative == "outputs/plan_author.json":
                return plan, plan_raw
            raise CONTINUATION.ContinuationError("stop after observing selected historical draft")
        accepted = {"type": "final_map_accepted", "payload": {"revision": 1,
            "review_phase": "final_map_review_citation_0001"}}
        with mock.patch.object(CONTINUATION, "_read_json", side_effect=read_until_selected):
            assert not CONTINUATION._final_map_acceptance_valid(root, [prepared, review_event], context, plan, accepted)
        assert reads == ["outputs/final-map-citation-0001.json"]
        appended = []
        with mock.patch.object(CONTINUATION, "_final_map_acceptance_valid", return_value=True), \
             mock.patch.object(CONTINUATION, "_events", return_value=[prepared, review_event]), \
             mock.patch.object(CONTINUATION, "_append", side_effect=lambda _root, _type, _payload, artifacts:
                               appended.append(artifacts) or {"type": "final_map_accepted"}):
            result = CONTINUATION._final_map_finalize(root, context, plan, [prepared, review_event])
        assert result["type"] == "final_map_accepted"
        assert {row["path"] for row in appended[0]} == expected


@unittest.skipUnless(Path("/private/tmp/atlas-final-map-assembly-20261015/resumption-repairs-20261015/prototype6/isolated-task-final2").is_dir(),
                     "captured109 source-transition proof input unavailable")
class Captured109ManagedSourceTransitionTests(unittest.TestCase):
    """Public P7 admission, fail-closed receipts, and restart behavior on frozen109."""

    proof_root = Path("/private/tmp/atlas-final-map-assembly-20261015/resumption-repairs-20261015/prototype7")
    captured_run = proof_root / "proofs/correction46-final/public109-final-actor/run"
    legacy_receipt_run = Path("/private/tmp/atlas-final-map-assembly-20261015/resumption-repairs-20261015/prototype6/isolated-task-final3")
    frozen_root = Path("/private/tmp/atlas-final-map-assembly-20261015/resumption-repairs-20261015/frozen109")
    frozen_manifest = Path("/private/tmp/atlas-final-map-assembly-20261015/resumption-repairs-20261015/frozen109-files.json")
    task_file = Path("/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt")
    intake = Path("/private/tmp/atlas-discount-lifecycle-task-20261012/run")
    engine = Path("/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json")
    repo_path = "/Users/kamenkamenov/taggable-api"
    db_path = "/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite"

    @staticmethod
    def _tree(root):
        return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob("*") if path.is_file()}

    def _command(self, run, action, *extra):
        return [sys.executable, "-B", os.fspath(CONTINUATION_PATH), action,
                "--repo", self.repo_path, "--db", self.db_path,
                "--task-file", os.fspath(self.task_file), "--intake-run", os.fspath(self.intake),
                "--run-dir", os.fspath(run), "--engine-manifest", os.fspath(self.engine), *extra]

    def _public(self, run, action, *extra):
        return subprocess.run(self._command(run, action, *extra), capture_output=True, text=True, timeout=90)

    def _assert_frozen_prefix(self, run):
        rows = json.loads(self.frozen_manifest.read_text())
        for row in rows:
            saved = run / row["path"]
            self.assertTrue(saved.is_file(), row["path"])
            self.assertEqual(saved.stat().st_size, row["bytes"], row["path"])
            self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), row["sha256"], row["path"])

    def _fresh109(self, parent):
        run = parent / "captured109-p7"
        shutil.copytree(self.frozen_root, run)
        shutil.copy2(self.legacy_receipt_run / "inputs/managed-source-transition-receipt.json",
                     run / "inputs/managed-source-transition-receipt.json")
        return run

    def _admit_args(self, run):
        index = run / "inputs/engine-transition/citation-schema-failure-files.json"
        return ("--prepare-only", "--max-worker-calls", "1", "--adopt-final-map-feedback-executor",
                "--citation-schema-failure-index", os.fspath(index),
                "--citation-schema-failure-index-sha256", "6b7e417c9eff9b8e23266a0e55028ccc7882deeea1ed3c06a70ccb7367f07fb1")

    def test_captured109_public_admission_preserves_legacy_retry_and_reenters_without_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self._fresh109(Path(temp))
            self._assert_frozen_prefix(run)
            before = self._tree(run)
            unadmitted = self._public(run, "status")
            self.assertEqual(unadmitted.returncode, 2)
            self.assertIn("provided engine manifest differs from the immutable run binding",
                          unadmitted.stderr.lower())
            self.assertEqual(self._tree(run), before)

            admitted = self._public(run, "resume", *self._admit_args(run))
            self.assertEqual(admitted.returncode, 0, admitted.stderr)
            status = json.loads(admitted.stdout)
            self.assertEqual(status["events"], 111)
            self.assertEqual(status["status"], "final_map_author_citation_schema_retry_0001")
            self.assertNotEqual(status["source_identity_sha256"], status["operating_source_identity_sha256"])
            self._assert_frozen_prefix(run)
            after_admission = self._tree(run)
            self.assertEqual(json.loads((run / "events/000111.json").read_text())["type"],
                             "managed_instruction_source_transition_admitted")

            repeated_status = self._public(run, "status")
            self.assertEqual(repeated_status.returncode, 0, repeated_status.stderr)
            repeated = self._public(run, "resume", "--prepare-only", "--max-worker-calls", "1")
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(self._tree(run), after_admission)
            self._assert_frozen_prefix(run)

    def test_captured109_interrupted_admission_replays_once_from_archived_actor(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self._fresh109(Path(temp))
            actor = json.loads((self.captured_run / "events/000110.json").read_text())
            self.assertEqual(actor["type"], "continuation_executor_resumed")
            self.assertEqual(actor["payload"]["adoption_kind"], "managed_instruction_source_transition")
            self.assertEqual(actor["payload"]["executor"]["sha256"], CONTINUATION._sha(CONTINUATION_PATH.read_bytes()))
            run.joinpath("events/000110.json").write_text(json.dumps(actor, sort_keys=True, separators=(",", ":")) + "\n")
            archive_path = actor["payload"]["actor_archive_path"]
            shutil.copy2(self.captured_run / archive_path, run / archive_path)
            before = self._tree(run)
            recorded_executor = Path(actor["payload"]["executor"]["path"])
            self.assertEqual(recorded_executor.read_bytes(), CONTINUATION_PATH.read_bytes())
            if recorded_executor.resolve() != CONTINUATION_PATH.resolve():
                moved = self._public(run, "resume", *self._admit_args(run))
                self.assertEqual(moved.returncode, 2, moved.stderr)
                self.assertIn("P7 source handoff requires the exact admitted P6 actor and receipt checkpoint",
                              moved.stderr)
                self.assertEqual(self._tree(run), before)
            command = self._command(run, "resume", *self._admit_args(run))
            command[2] = os.fspath(recorded_executor)
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list((run / "events").glob("*.json"))), 111)
            self.assertEqual(self._tree(run)["events/000110.json"], before["events/000110.json"])
            self.assertEqual(json.loads((run / "events/000111.json").read_text())["type"],
                             "managed_instruction_source_transition_admitted")
            self.assertEqual(json.loads((run / "events/000111.json").read_text())["type"],
                             "managed_instruction_source_transition_admitted")
            self._assert_frozen_prefix(run)

    def test_captured109_missing_malformed_tampered_and_wrong_base_receipts_refuse_without_writes(self):
        mutations = {
            "missing": lambda run, receipt: (run / "inputs/managed-source-transition-receipt.json").unlink(),
            "malformed_reference": lambda run, receipt: receipt.__setitem__("repair_envelope", []),
            "tampered_reference": lambda run, receipt: receipt["repair_envelope"].__setitem__("sha256", "0" * 64),
            "wrong_base": lambda run, receipt: receipt["transition"].__setitem__(
                "base_event_sha256", json.loads((run / "events/000108.json").read_text())["event_sha256"]),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                run = Path(temp) / "receipt-case"
                shutil.copytree(self.frozen_root, run)
                receipt_path = run / "inputs/managed-source-transition-receipt.json"
                shutil.copy2(self.legacy_receipt_run / "inputs/managed-source-transition-receipt.json", receipt_path)
                receipt = json.loads(receipt_path.read_text())
                mutate(run, receipt)
                if receipt_path.exists():
                    receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
                before = self._tree(run)
                result = self._public(run, "status")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("AttributeError", result.stderr)
                self.assertEqual(self._tree(run), before)


class Captured111CitationAdditionsTests(unittest.TestCase):
    """Captured P7 proposal path: deterministic preservation and bounded routing."""

    frozen = Path("/private/tmp/atlas-final-map-assembly-20261015/resumption-repairs-20261015/frozen111")
    manifest = Path("/private/tmp/atlas-discount-lifecycle-task-20261012/completed-worker-recovery-v2/current-engine-manifest.json")
    repo = "/Users/kamenkamenov/taggable-api"
    db = "/Users/kamenkamenov/memory-knowledge/.atlas-state/taggable-api/current-final/atlas.sqlite"
    task = "/private/tmp/atlas-discount-lifecycle-task-20261012/task.txt"
    intake = "/private/tmp/atlas-discount-lifecycle-task-20261012/run"

    def _new_run(self, parent: Path) -> Path:
        run = parent.resolve() / "captured111-p7"
        shutil.copytree(self.frozen, run)
        return run

    @classmethod
    def setUpClass(cls):
        # This captured protocol test must load the exact modules named by its
        # immutable engine manifest.  The test module's legacy import path may
        # already have loaded same-named modules from the candidate checkout.
        requested, raw, engine_root = CONTINUATION._validate_engine_manifest(cls.manifest)
        for name, relative in {
            "csharp_facts": "csharp_facts.py", "atlas": "atlas.py",
            "route_coordinator": "route_coordinator.py", "route_batch": "route_batch.py",
            "route_autorun": "route_autorun.py", "task_intake": "task_intake.py",
            "runtime_index_launch": "runtime_index_launch.py", "atlas_workspace": "atlas_workspace.py",
            "question_coordinator": "question_coordinator.py", "compiler_index_launch": "compiler_index_launch.py",
            "atlas_launch": "atlas_launch.py", "route_batch_autorun": "route_batch_autorun.py",
            "route_batch_launch": "route_batch_launch.py",
        }.items():
            present = sys.modules.get(name)
            expected = (engine_root / relative).resolve()
            if present is not None and Path(getattr(present, "__file__", "")).resolve() != expected:
                sys.modules.pop(name, None)
        CONTINUATION.atlas = None
        CONTINUATION.route_autorun = None
        CONTINUATION.route_batch = None
        CONTINUATION.route_coordinator = None
        CONTINUATION.task_intake = None
        CONTINUATION._load_verified_engine(engine_root)
        CONTINUATION._ENGINE_MANIFEST_RAW = raw
        CONTINUATION._ENGINE_MANIFEST_PATH = cls.manifest.resolve(strict=True)
        CONTINUATION._ENGINE_ROOT = engine_root
        CONTINUATION._ENGINE_BOUND = True

    @staticmethod
    def _tree_hashes(root: Path):
        return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob("*") if path.is_file()}

    def _make_native_worker(self, run, phase, role, model, request, answer):
        return AtlasCliTests.synthetic_native_final_worker(self, run, phase, role, model, request, answer)

    def _resume_from_distinct_executor_path(self, run, args, native_check, temp_root, attempt):
        safe_root = Path(tempfile.mkdtemp(prefix=f"atlas-p7-relocated-{attempt}-", dir="/private/tmp"))
        unadmitted_path = safe_root / "unadmitted-task_continuation.py"
        shutil.copy2(CONTINUATION_PATH, unadmitted_path)
        unadmitted_spec = importlib.util.spec_from_file_location(f"unadmitted_continuation_{attempt}", unadmitted_path)
        unadmitted = importlib.util.module_from_spec(unadmitted_spec)
        unadmitted_spec.loader.exec_module(unadmitted)
        before_unadmitted = self._tree_hashes(run)
        with mock.patch.object(unadmitted.route_autorun, "run_worker",
                side_effect=AssertionError("unadmitted executor must not dispatch a provider")):
            with self.assertRaises(unadmitted.ContinuationError):
                unadmitted.resume(*args, max_worker_calls=1, engine_manifest=os.fspath(self.manifest))
        self.assertEqual(self._tree_hashes(run), before_unadmitted)
        relocated_path = safe_root / "task_continuation.py"
        shutil.copy2(CONTINUATION_PATH, relocated_path)
        spec = importlib.util.spec_from_file_location(f"relocated_continuation_{attempt}", relocated_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with (mock.patch.object(module, "_verify_final_map_native_job", side_effect=native_check),
              mock.patch.object(module.route_autorun, "run_worker",
                side_effect=AssertionError("accepted review reentry must not dispatch a provider"))):
            result = module.resume(*args, max_worker_calls=1, engine_manifest=os.fspath(self.manifest),
                                   adopt_final_map_feedback_executor=True)
        handoff = next(event for event in reversed(module._events(run))
            if event.get("type") == "continuation_executor_resumed")
        self.assertEqual(handoff["payload"]["adoption_kind"], "final_map_citation_accepted_review_finalize")
        self.assertEqual(handoff["payload"]["attempt"], attempt)
        self.assertEqual(handoff["payload"]["executor"]["path"], os.fspath(relocated_path.resolve()))
        self.assertNotEqual(handoff["payload"]["previous_executor"]["path"],
                            handoff["payload"]["executor"]["path"])
        return module, result, safe_root

    def test_revision2_rejection_selects_additions_producer_without_transition_gate(self):
        """The source-bound repair fixes the existing citation producer, not only P7 admission."""
        with tempfile.TemporaryDirectory() as temp:
            run = self._new_run(Path(temp))
            context, events = CONTINUATION._load(run, self.repo, self.db, self.task, self.intake)
            plan, _ = CONTINUATION._read_json(run / "outputs/plan_author.json", "captured accepted plan")
            without_transition = [event for event in events if not (
                event.get("type") == "continuation_executor_resumed"
                and event.get("payload", {}).get("adoption_kind") == "final_map_citation_additions_p7")]
            second_rejection = next(event for event in without_transition
                if event.get("type") == "final_map_revision_0002_review_completed")
            clean_producer_history = [event for event in without_transition
                if event.get("sequence", 0) <= second_rejection.get("sequence", 0)]
            self.assertEqual(CONTINUATION._final_map_next_type(clean_producer_history, context, plan),
                "final_map_citation_additions_prepare")
            # The source-bound saved full-map schema-recovery request remains a
            # readable legacy continuation until explicit P7 handoff supersedes it.
            self.assertEqual(CONTINUATION._final_map_next_type(without_transition, context, plan),
                "final_map_author_citation_schema_retry_0001")

    def test_empty_proposal_consumes_one_slot_then_saved_attempt2_recovers_without_dispatch(self):
        """Malformed attempt one is bounded; attempt two survives a saved-worker interruption."""
        with tempfile.TemporaryDirectory() as temp:
            run = self._new_run(Path(temp))
            args = (self.repo, self.db, self.task, self.intake, os.fspath(run))
            CONTINUATION.resume(*args, max_worker_calls=1, engine_manifest=os.fspath(self.manifest),
                prepare_only=True, adopt_final_map_feedback_executor=True)
            calls = []
            original_native_check = CONTINUATION._verify_final_map_native_job

            def native_check(root, request, role, model, phase, expected,
                             thread_id, register_path, register_sha, artifact_dir):
                if not (phase.startswith("final_map_author_citation_additions_")
                        or phase.startswith("final_map_review_citation_")):
                    return original_native_check(root, request, role, model, phase, expected,
                        thread_id, register_path, register_sha, artifact_dir)
                module = CONTINUATION.route_autorun
                cli_path = run / "pinned-cli"
                old_cli, old_sha = module.CLI, module.CLI_SHA256
                module.CLI = os.fspath(cli_path)
                module.CLI_SHA256 = hashlib.sha256(cli_path.read_bytes()).hexdigest()
                try:
                    return original_native_check(root, request, role, model, phase, expected,
                        thread_id, register_path, register_sha, artifact_dir)
                finally:
                    module.CLI, module.CLI_SHA256 = old_cli, old_sha

            def edge(role, prompt, job_path, timeout_seconds, output_schema):
                phase = Path(job_path).name
                attempt = int(phase.rsplit("_", 1)[1])
                map_path, _text_path, review_request_path, _review_path = CONTINUATION._citation_additions_paths(attempt)
                request_path = run / f"inputs/final-map-citation-additions-{attempt:04d}.json"
                request, _ = CONTINUATION._read_json(request_path, "attempt-bound addition request")
                if phase.startswith("final_map_author_citation_additions_"):
                    if attempt == 1:
                        value = {"schema_version": 1, "base_map_sha256": request["base_map_sha256"],
                            "catalogue_sha256": request["catalogue_sha256"], "additions": []}
                    else:
                        base, _ = CONTINUATION._read_json(run / "outputs/final-map-revision-0002.json", "base map")
                        finding = base["findings"][0]
                        evidence_id = next(item for item in request["evidence_ids"]
                            if item not in finding["evidence_refs"])
                        value = {"schema_version": 1, "base_map_sha256": request["base_map_sha256"],
                            "catalogue_sha256": request["catalogue_sha256"],
                            "additions": [{"finding_id": finding["finding_id"], "evidence_ids": [evidence_id]}]}
                    answer = json.dumps(value, sort_keys=True)
                    model = "gpt-6-luna"
                else:
                    review_request, _ = CONTINUATION._read_json(run / review_request_path, "independent review request")
                    draft, _ = CONTINUATION._read_json(run / map_path, "assembled map")
                    judgments = [{"obligation_id": row["obligation_id"], "decision": "supported",
                        "finding_ids": row["finding_ids"], "uncertainty": "Synthetic review edge."}
                        for row in draft["obligations"]]
                    answer = json.dumps({"decision": "accepted", "reviewer_identity": review_request["reviewer_identity"],
                        "task_sha256": review_request["task_sha256"],
                        "source_identity_sha256": review_request["source_identity_sha256"],
                        "plan_sha256": review_request["plan_sha256"], "map_sha256": review_request["map_sha256"],
                        "finding_link_policy": review_request["finding_link_policy"],
                        "obligation_judgments": judgments,
                        "basis": "Synthetic review edge for saved-worker recovery; it makes no factual judgment."}, sort_keys=True)
                    model = "gpt-6.1-sol"
                calls.append(phase)
                _req, result, _event, _register, _sha, _digests = self._make_native_worker(
                    run, phase, role, model, request if model == "gpt-6-luna" else review_request, answer)
                for path in (run / "outputs" / f"{phase}.txt", run / "outputs" / f"{phase}-worker.json"):
                    path.unlink(missing_ok=True)
                return {**result, "final_text": answer}

            with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                 mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=edge):
                first = CONTINUATION.resume(*args, max_worker_calls=1, engine_manifest=os.fspath(self.manifest))
            self.assertEqual(calls, ["final_map_author_citation_additions_0001"])
            rejected = next(event for event in CONTINUATION._events(run)
                if event.get("type") == "final_map_citation_additions_rejected")
            self.assertEqual(rejected["payload"]["attempt"], 1)
            self.assertEqual(first["status"], "final_map_citation_additions_prepare")
            with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check):
                prepared = CONTINUATION.resume(*args, max_worker_calls=1,
                    engine_manifest=os.fspath(self.manifest), prepare_only=True)
            self.assertEqual(prepared["status"], "final_map_author_citation_additions_0002")
            context, _ = CONTINUATION._load(run, self.repo, self.db, self.task, self.intake)
            request, _ = CONTINUATION._read_json(
                run / "inputs/final-map-citation-additions-0002.json", "attempt two request")
            phase = "final_map_author_citation_additions_0002"
            # Save the provider-complete event separately from the consumer to model interruption.
            with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                 mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=edge):
                CONTINUATION._record_worker(run, "luna_draft", request["prompt"], request["schema"], phase, 30)
            with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                 mock.patch.object(CONTINUATION.route_autorun, "run_worker",
                    side_effect=AssertionError("saved attempt two must not be redispatched")):
                recovered = CONTINUATION.resume(*args, max_worker_calls=1, engine_manifest=os.fspath(self.manifest))
            self.assertEqual(recovered["status"], "final_map_citation_review_prepare")
            with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                 mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=edge):
                accepted = CONTINUATION.resume(*args, max_worker_calls=2, engine_manifest=os.fspath(self.manifest))
            self.assertEqual(accepted["status"], "completed")
            self.assertTrue(accepted["task_complete"])
            before_repeat = self._tree_hashes(run)
            with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check):
                again = CONTINUATION.resume(*args, max_worker_calls=1, engine_manifest=os.fspath(self.manifest))
            self.assertTrue(again["task_complete"])
            self.assertEqual(before_repeat, self._tree_hashes(run))

    def test_captured111_additions_proposal_assembles_and_routes_review_with_repeat_safety(self):
        """External model edges are labeled synthetic; public consumer/review/finalize stay real."""
        if not (self.frozen / "events/000111.json").is_file():
            self.skipTest("Immutable captured111 checkpoint unavailable")
        original_native_check = CONTINUATION._verify_final_map_native_job

        selected_case = os.environ.get("ATLAS_CITATION_ADDITIONS_CASE")
        decisions = (selected_case,) if selected_case else ("accepted", "rejected")
        self.assertTrue(set(decisions) <= {"accepted", "rejected"})
        for decision in decisions:
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as temp:
                run = self._new_run(Path(temp))
                args = (self.repo, self.db, self.task, self.intake, os.fspath(run))
                first = CONTINUATION.resume(*args, max_worker_calls=1, engine_manifest=os.fspath(self.manifest),
                    prepare_only=True, adopt_final_map_feedback_executor=True)
                self.assertEqual(first["status"], "final_map_author_citation_additions_0001")
                request, request_raw = CONTINUATION._read_json(
                    run / "inputs/final-map-citation-additions-0001.json", "captured P7 additions request")
                self.assertNotIn("uniqueItems", json.dumps(request["schema"]))
                before_repeat = self._tree_hashes(run)
                repeated = CONTINUATION.resume(*args, max_worker_calls=1,
                    engine_manifest=os.fspath(self.manifest), prepare_only=True)
                self.assertEqual(repeated["status"], "final_map_author_citation_additions_0001")
                self.assertEqual(before_repeat, self._tree_hashes(run))

                simulated_calls = []
                def provider_edge(role, prompt, job_path, timeout_seconds, output_schema):
                    phase = Path(job_path).name
                    attempt = int(phase.rsplit("_", 1)[1])
                    map_path, _explanation_path, review_request_path, _review_path = \
                        CONTINUATION._citation_additions_paths(attempt)
                    if phase.startswith("final_map_author_citation_additions_"):
                        request, _ = CONTINUATION._read_json(
                            run / f"inputs/final-map-citation-additions-{attempt:04d}.json", "simulated proposal request")
                        base, _ = CONTINUATION._read_json(
                            run / "outputs/final-map-revision-0002.json", "preserved P6 base map")
                        finding = base["findings"][0]
                        used = set(finding["evidence_refs"])
                        previous_map = run / f"outputs/final-map-citation-{attempt-1:04d}.json"
                        if attempt > 1 and previous_map.is_file():
                            previous, _ = CONTINUATION._read_json(previous_map, "preserved prior attempt map")
                            used.update(previous["findings"][0]["evidence_refs"])
                        evidence_id = next(item for item in request["evidence_ids"] if item not in used)
                        answer_value = {"schema_version": 1,
                            "base_map_sha256": request["base_map_sha256"],
                            "catalogue_sha256": request["catalogue_sha256"],
                            "additions": [{"finding_id": finding["finding_id"], "evidence_ids": [evidence_id]}]}
                        answer = json.dumps(answer_value, ensure_ascii=False, sort_keys=True)
                        model = "gpt-6-luna"
                    elif phase.startswith("final_map_review_citation_"):
                        request, _ = CONTINUATION._read_json(
                            run / review_request_path, "simulated complete-map review request")
                        draft, _ = CONTINUATION._read_json(
                            run / map_path, "code-assembled full map")
                        judgments = []
                        for obligation in draft["obligations"]:
                            self.assertTrue(obligation["finding_ids"],
                                "captured case should keep every original obligation explicitly linked")
                            judgments.append({"obligation_id": obligation["obligation_id"],
                                "decision": "supported", "finding_ids": obligation["finding_ids"],
                                "uncertainty": "Synthetic review edge; factual adequacy is not assessed here."})
                        answer_value = {"decision": "accepted" if attempt > 1 else decision,
                            "reviewer_identity": request["reviewer_identity"],
                            "task_sha256": request["task_sha256"],
                            "source_identity_sha256": request["source_identity_sha256"],
                            "plan_sha256": request["plan_sha256"],
                            "map_sha256": request["map_sha256"],
                            "finding_link_policy": request["finding_link_policy"],
                            "obligation_judgments": judgments,
                            "basis": "Synthetic external-edge response for code-path verification only; no factual Sol judgment is claimed."}
                        answer = json.dumps(answer_value, ensure_ascii=False, sort_keys=True)
                        model = "gpt-6.1-sol"
                    else:
                        raise AssertionError(f"unexpected simulated external edge: {phase}")
                    simulated_calls.append(phase)
                    _req, result, _event, _register, _register_sha, _digests = self._make_native_worker(
                        run, phase, role, model, request, answer)
                    (run / "outputs" / f"{phase}.txt").unlink()
                    (run / "outputs" / f"{phase}-worker.json").unlink()
                    return {**result, "final_text": answer}

                def native_check(root, request, role, model, phase, expected,
                                 thread_id, register_path, register_sha, artifact_dir):
                    if not (phase.startswith("final_map_author_citation_additions_")
                            or phase.startswith("final_map_review_citation_")):
                        return original_native_check(root, request, role, model, phase, expected,
                            thread_id, register_path, register_sha, artifact_dir)
                    module = CONTINUATION.route_autorun
                    cli_path = run / "pinned-cli"
                    old_cli, old_sha = module.CLI, module.CLI_SHA256
                    module.CLI = os.fspath(cli_path)
                    module.CLI_SHA256 = hashlib.sha256(cli_path.read_bytes()).hexdigest()
                    try:
                        return original_native_check(root, request, role, model, phase, expected,
                            thread_id, register_path, register_sha, artifact_dir)
                    finally:
                        module.CLI, module.CLI_SHA256 = old_cli, old_sha

                if decision == "accepted":
                    # Save a genuine-shaped native completion, then interrupt before the
                    # proposal consumer. Reentry must consume it without another edge call.
                    context, _ = CONTINUATION._load(run, self.repo, self.db, self.task, self.intake)
                    phase = "final_map_author_citation_additions_0001"
                    request, _ = CONTINUATION._read_json(
                        run / "inputs/final-map-citation-additions-0001.json", "interrupted proposal request")
                    with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                         mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=provider_edge):
                        _value, interrupted_worker = CONTINUATION._record_worker(run, "luna_draft",
                            request["prompt"], request["schema"], phase, 30)
                    self.assertIn("final_map_author_citation_additions_0001_worker_completed",
                        [event.get("type") for event in CONTINUATION._events(run)])
                    with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                         mock.patch.object(CONTINUATION.route_autorun, "run_worker",
                            side_effect=AssertionError("saved proposal must not be redispatched")):
                        recovered = CONTINUATION.resume(*args, max_worker_calls=1,
                            engine_manifest=os.fspath(self.manifest))
                    self.assertEqual(recovered["status"], "final_map_citation_review_prepare")
                    with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                         mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=provider_edge), \
                         mock.patch.object(CONTINUATION, "_final_map_finalize",
                            side_effect=CONTINUATION.ContinuationError("saved accepted review interruption")):
                        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "saved accepted review interruption"):
                            CONTINUATION.resume(*args, max_worker_calls=2,
                                engine_manifest=os.fspath(self.manifest))
                    relocated_module, status, relocated_root = self._resume_from_distinct_executor_path(
                        run, args, native_check, temp, attempt=1)
                else:
                    with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                         mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=provider_edge):
                        status = CONTINUATION.resume(*args, max_worker_calls=2, engine_manifest=os.fspath(self.manifest))
                self.assertEqual(interrupted_worker.get("payload", {}).get("phase") if decision == "accepted" else None,
                    "final_map_author_citation_additions_0001" if decision == "accepted" else None)


                events = CONTINUATION._events(run)
                assembled_event = next(item for item in events
                    if item.get("type") == "final_map_citation_additions_assembled")
                proposal, _ = CONTINUATION._read_json(
                    run / "outputs/final-map-citation-additions-0001.json", "simulated proposal result")
                base, _ = CONTINUATION._read_json(
                    run / "outputs/final-map-revision-0002.json", "preserved P6 base map")
                assembled, _ = CONTINUATION._read_json(
                    run / "outputs/final-map-citation-0001.json", "deterministic P7 assembly")
                self.assertEqual(assembled_event["payload"]["proposal_sha256"],
                    hashlib.sha256(CONTINUATION._json_bytes(proposal)).hexdigest())
                self.assertEqual(assembled["findings"][1:], base["findings"][1:])
                protected = json.loads(json.dumps(assembled))
                old = json.loads(json.dumps(base))
                for row in protected["findings"]:
                    row["evidence_refs"] = []
                for row in old["findings"]:
                    row["evidence_refs"] = []
                self.assertEqual(protected, old, "all parsed values except citation refs must be preserved")
                review_event = next(item for item in events
                    if item.get("type") == "final_map_citation_review_completed")
                self.assertEqual(review_event["payload"]["decision"], decision)
                self.assertEqual(simulated_calls,
                    ["final_map_author_citation_additions_0001", "final_map_review_citation_0001"])
                self.assertFalse(status["task_complete"] if decision == "rejected" else False)
                if decision == "accepted":
                    self.assertEqual(status["status"], "completed")
                    self.assertTrue(status["task_complete"])
                    with mock.patch.object(relocated_module, "_verify_final_map_native_job", side_effect=native_check):
                        finalized = relocated_module.resume(*args, max_worker_calls=1,
                            engine_manifest=os.fspath(self.manifest))
                    self.assertTrue(finalized["task_complete"])
                    stable = self._tree_hashes(run)
                    with mock.patch.object(relocated_module, "_verify_final_map_native_job", side_effect=native_check):
                        again = relocated_module.resume(*args, max_worker_calls=1,
                            engine_manifest=os.fspath(self.manifest))
                    self.assertTrue(again["task_complete"])
                    self.assertEqual(stable, self._tree_hashes(run))
                    shutil.rmtree(relocated_root)
                else:
                    self.assertEqual(status["status"], "final_map_citation_additions_prepare")
                    first_map, first_raw = CONTINUATION._read_json(
                        run / "outputs/final-map-citation-0001.json", "preserved rejected attempt map")
                    first_review, first_review_raw = CONTINUATION._read_json(
                        run / "outputs/final-map-review-citation-0001.json", "preserved rejected attempt review")
                    with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check):
                        second_prepared = CONTINUATION.resume(*args, max_worker_calls=1,
                            engine_manifest=os.fspath(self.manifest), prepare_only=True)
                    self.assertEqual(second_prepared["status"], "final_map_author_citation_additions_0002")
                    second_request, _ = CONTINUATION._read_json(
                        run / "inputs/final-map-citation-additions-0002.json", "second bounded proposal request")
                    self.assertEqual(second_request["prior_review_sha256"],
                        hashlib.sha256(first_review_raw).hexdigest())
                    self.assertIn("ACTIONABLE FEEDBACK FROM THE PRIOR BOUNDED ATTEMPT", second_request["prompt"])
                    with mock.patch.object(CONTINUATION, "_verify_final_map_native_job", side_effect=native_check), \
                         mock.patch.object(CONTINUATION.route_autorun, "run_worker", side_effect=provider_edge), \
                         mock.patch.object(CONTINUATION, "_final_map_finalize",
                            side_effect=CONTINUATION.ContinuationError("saved accepted review interruption")):
                        with self.assertRaisesRegex(CONTINUATION.ContinuationError, "saved accepted review interruption"):
                            CONTINUATION.resume(*args, max_worker_calls=2,
                                engine_manifest=os.fspath(self.manifest))
                    relocated_module, accepted, relocated_root = self._resume_from_distinct_executor_path(
                        run, args, native_check, temp, attempt=2)
                    self.assertEqual(accepted["status"], "completed")
                    self.assertTrue(accepted["task_complete"])
                    self.assertEqual(simulated_calls[-2:],
                        ["final_map_author_citation_additions_0002", "final_map_review_citation_0002"])
                    self.assertEqual((run / "outputs/final-map-citation-0001.json").read_bytes(), first_raw)
                    self.assertEqual((run / "outputs/final-map-review-citation-0001.json").read_bytes(), first_review_raw)
                    # Alter only review 2's provenance to cite attempt 1. The
                    # deterministic verifier must reject the cross-attempt chain.
                    review2_path = run / "inputs/final-map-review-citation-0002.json"
                    original_review2_raw = review2_path.read_bytes()
                    review2, _ = CONTINUATION._read_json(review2_path, "attempt two review request")
                    review1, _ = CONTINUATION._read_json(
                        run / "inputs/final-map-review-citation-0001.json", "attempt one review request")
                    review2["citation_additions_provenance"] = review1["citation_additions_provenance"]
                    review2_path.write_bytes(CONTINUATION._json_bytes(review2))
                    try:
                        bound_context, _ = CONTINUATION._read_json(run / "context.json", "bound captured context")
                        plan_raw = (run / "outputs/plan_author.json").read_bytes()
                        with self.assertRaisesRegex(CONTINUATION.ContinuationError,
                                "a committed continuation artifact changed"):
                            CONTINUATION._verified_citation_additions_review(
                                run, CONTINUATION._events(run), bound_context, plan_raw, 2)
                    finally:
                        review2_path.write_bytes(original_review2_raw)
                    with mock.patch.object(relocated_module, "_verify_final_map_native_job", side_effect=native_check), \
                         mock.patch.object(relocated_module.route_autorun, "run_worker",
                            side_effect=AssertionError("attempt two finalization must not dispatch")):
                        finalized = relocated_module.resume(*args, max_worker_calls=1,
                            engine_manifest=os.fspath(self.manifest))
                    self.assertTrue(finalized["task_complete"])
                    stable = self._tree_hashes(run)
                    with mock.patch.object(relocated_module, "_verify_final_map_native_job", side_effect=native_check), \
                         mock.patch.object(relocated_module.route_autorun, "run_worker",
                            side_effect=AssertionError("completed attempt two must not dispatch")):
                        again = relocated_module.resume(*args, max_worker_calls=1,
                            engine_manifest=os.fspath(self.manifest))
                    self.assertTrue(again["task_complete"])
                    self.assertEqual(stable, self._tree_hashes(run))
                    shutil.rmtree(relocated_root)

    def test_captured111_proposal_refusals_name_the_offending_boundary(self):
        run = self.frozen
        request, _ = CONTINUATION._read_json(
            run / "inputs/final-map-citation-additions-0001.json", "captured P7 request") if \
            (run / "inputs/final-map-citation-additions-0001.json").is_file() else (None, None)
        if request is None:
            # The frozen111 prefix predates P7; use the exact prepared request from its public isolated copy.
            prepared = Path("/private/tmp/atlas-final-map-assembly-20261015/resumption-repairs-20261015/prototype7/isolated-task-p7-final")
            request, _ = CONTINUATION._read_json(
                prepared / "inputs/final-map-citation-additions-0001.json", "publicly prepared P7 request")
            run = prepared
        base, _ = CONTINUATION._read_json(run / "outputs/final-map-revision-0002.json", "captured citation base")
        good = {"schema_version": 1, "base_map_sha256": request["base_map_sha256"],
            "catalogue_sha256": request["catalogue_sha256"], "additions": [{
                "finding_id": base["findings"][0]["finding_id"],
                "evidence_ids": [next(item for item in request["evidence_ids"]
                    if item not in base["findings"][0]["evidence_refs"])]}]}
        cases = [
            ({**good, "additions": []}, "at least one finding-reference addition"),
            ({**good, "base_map_sha256": "0" * 64}, "expected base="),
            ({**good, "additions": [{"finding_id": ["bad"], "evidence_ids": ["x"]}]}, "finding_id=['bad'] is unknown"),
            ({**good, "additions": [{"finding_id": good["additions"][0]["finding_id"],
                "evidence_ids": ["outside-catalogue"]}]}, "outside the admitted catalogue"),
            ({**good, "additions": [{"finding_id": good["additions"][0]["finding_id"],
                "evidence_ids": [good["additions"][0]["evidence_ids"][0]] * 2}]}, "repeat evidence IDs"),
        ]
        for proposal, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(CONTINUATION.ContinuationError) as raised:
                    CONTINUATION._validate_citation_additions(proposal, request, base)
                self.assertIn(message, str(raised.exception))
