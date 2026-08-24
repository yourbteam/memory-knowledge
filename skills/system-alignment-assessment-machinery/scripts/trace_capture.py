#!/usr/bin/env python3
"""Create and verify immutable code-grounded alignment traces."""
from __future__ import annotations
import argparse, hashlib, json, sys
from copy import deepcopy
from pathlib import Path
from typing import Any

CONTRACT=1; ARTIFACT_TYPE="system-alignment-implementation-trace"; INVENTORY_TYPE="system-alignment-path-inventory"
class TraceCaptureError(RuntimeError): pass
def _canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
def _document(v): return json.dumps(v,indent=2,sort_keys=True).encode()+b"\n"
def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def _load(p,label):
    try: v=json.loads(p.read_bytes())
    except (OSError,UnicodeDecodeError,json.JSONDecodeError) as e: raise TraceCaptureError(f"{label} is unavailable or invalid JSON: {e}") from None
    if type(v) is not dict: raise TraceCaptureError(f"{label} must contain one JSON object")
    return v
def _text(v,label):
    if type(v) is not str or not v: raise TraceCaptureError(f"{label} must be a nonempty string")
    return v
def _inventory(ref):
    if type(ref) is not dict or set(ref)!={"path","sha256","artifact_sha256"}: raise TraceCaptureError("path_inventory reference fields changed")
    p=Path(_text(ref["path"],"path_inventory path"))
    if not p.is_absolute() or p.is_symlink() or not p.is_file(): raise TraceCaptureError(f"path_inventory must be an absolute regular file: {p}")
    observed=_sha(p)
    if observed!=ref["sha256"]: raise TraceCaptureError(f"path_inventory bytes changed: expected {ref['sha256']}, observed {observed}")
    value=_load(p,"path_inventory")
    if value.get("artifact_type")!=INVENTORY_TYPE or value.get("artifact_sha256")!=ref["artifact_sha256"] or value.get("status")!="path-inventory-ready": raise TraceCaptureError("path_inventory identity or status changed")
    return {"path":str(p),"sha256":observed,"artifact_sha256":ref["artifact_sha256"]},value
def _evidence(ref,stage_id):
    expected={"repository","path","sha256","start_line","end_line","excerpt_sha256","reason"}
    if type(ref) is not dict or set(ref)!=expected: raise TraceCaptureError(f"stage {stage_id} evidence fields changed")
    repository=_text(ref["repository"],f"stage {stage_id} repository"); reason=_text(ref["reason"],f"stage {stage_id} reason")
    p=Path(_text(ref["path"],f"stage {stage_id} evidence path"))
    if not p.is_absolute() or p.is_symlink() or not p.is_file(): raise TraceCaptureError(f"stage {stage_id} evidence must be an absolute regular file: {p}")
    observed=_sha(p)
    if observed!=ref["sha256"]: raise TraceCaptureError(f"stage {stage_id} evidence file bytes changed")
    try: lines=p.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as e: raise TraceCaptureError(f"stage {stage_id} evidence is not UTF-8: {e}") from None
    a,b=ref["start_line"],ref["end_line"]
    if type(a) is not int or type(b) is not int or a<1 or b<a or b>len(lines): raise TraceCaptureError(f"stage {stage_id} evidence line span is invalid")
    excerpt=hashlib.sha256("".join(lines[a-1:b]).encode()).hexdigest()
    if excerpt!=ref["excerpt_sha256"]: raise TraceCaptureError(f"stage {stage_id} evidence excerpt changed")
    return {"repository":repository,"path":str(p),"sha256":observed,"start_line":a,"end_line":b,"excerpt_sha256":excerpt,"reason":reason}
def create_from_value(spec):
    if type(spec) is not dict or set(spec)!={"schema_version","path_inventory","lane_role","traces"}: raise TraceCaptureError("trace specification fields changed")
    if spec["schema_version"]!=CONTRACT: raise TraceCaptureError(f"trace schema_version must be {CONTRACT}")
    inventory_ref,inventory=_inventory(spec["path_inventory"]); lane_role=spec["lane_role"]
    lane=next((p for p in inventory["paths"] if p["role"]==lane_role),None)
    if lane is None: raise TraceCaptureError(f"lane_role is absent from path inventory: {lane_role!r}")
    expected=[s["stage_id"] for s in lane["stages"]]; traces=spec["traces"]
    if type(traces) is not list or [t.get("stage_id") if type(t) is dict else None for t in traces]!=expected: raise TraceCaptureError("trace stage coverage or order changed")
    recorded=[]
    for i,trace in enumerate(traces):
        stage_id=expected[i]
        if set(trace)!={"stage_id","sequence","next_stage_id","evidence"} or trace["sequence"]!=i+1: raise TraceCaptureError(f"stage {stage_id} trace fields or sequence changed")
        successor=expected[i+1] if i+1<len(expected) else None
        if trace["next_stage_id"]!=successor: raise TraceCaptureError(f"stage {stage_id} successor changed")
        refs=trace["evidence"]
        if type(refs) is not list or not refs: raise TraceCaptureError(f"stage {stage_id} needs evidence")
        recorded.append({"stage_id":stage_id,"sequence":i+1,"next_stage_id":successor,"evidence":[_evidence(r,stage_id) for r in refs]})
    body={"schema_version":CONTRACT,"artifact_type":ARTIFACT_TYPE,"path_inventory":inventory_ref,"lane_role":lane_role,"traces":recorded,"status":"trace-complete"}
    return {**body,"artifact_sha256":hashlib.sha256(_canonical(body)).hexdigest()}
def create(path): return create_from_value(_load(path,"trace specification"))
def _write_once(v,p):
    p.parent.mkdir(parents=True,exist_ok=True)
    try:
        with p.open("xb") as f:f.write(_document(v))
    except FileExistsError: raise TraceCaptureError(f"trace already exists: {p}") from None
def verify(path):
    value=_load(path,"trace")
    if path.read_bytes()!=_document(value): raise TraceCaptureError("trace bytes are not canonical")
    expected={"schema_version","artifact_type","path_inventory","lane_role","traces","status","artifact_sha256"}
    if set(value)!=expected or value["artifact_type"]!=ARTIFACT_TYPE or value["status"]!="trace-complete": raise TraceCaptureError("trace identity, status, or fields changed")
    rebuilt=create_from_value({k:value[k] for k in ("schema_version","path_inventory","lane_role","traces")})
    if rebuilt!=value: raise TraceCaptureError("trace no longer matches live evidence")
    return value
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest="command",required=True);c=s.add_parser("create");c.add_argument("--spec",required=True,type=Path);c.add_argument("--output",required=True,type=Path);v=s.add_parser("verify");v.add_argument("trace",type=Path);a=p.parse_args(argv)
    try:
        if a.command=="create": value=create(a.spec);_write_once(value,a.output)
        else:value=verify(a.trace)
    except TraceCaptureError as e: print(str(e),file=sys.stderr);return 2
    print(json.dumps({"artifact_sha256":value["artifact_sha256"],"lane_role":value["lane_role"],"stage_count":len(value["traces"]),"status":value["status"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
