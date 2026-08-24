"""Deterministic trace-evidence choices for mapping questions."""
from __future__ import annotations
import hashlib,json
from pathlib import Path

class MappingEvidenceError(RuntimeError): pass
def load_trace(ref,role):
    if type(ref) is not dict or set(ref)!={"path","sha256","artifact_sha256"}: raise MappingEvidenceError(f"{role} trace reference fields changed")
    path=Path(ref.get("path",""))
    if not path.is_absolute() or path.is_symlink() or not path.is_file(): raise MappingEvidenceError(f"{role} trace path must be an absolute regular file")
    observed=hashlib.sha256(path.read_bytes()).hexdigest()
    if observed!=ref["sha256"]: raise MappingEvidenceError(f"{role} trace bytes changed")
    value=json.loads(path.read_text())
    if value.get("artifact_type")!="system-alignment-implementation-trace" or value.get("artifact_sha256")!=ref["artifact_sha256"] or value.get("lane_role")!=role or value.get("status")!="trace-complete": raise MappingEvidenceError(f"{role} trace identity or status changed")
    choices=[]
    for trace in value["traces"]:
        for position,evidence in enumerate(trace["evidence"],1):
            choices.append({"evidence_id":f"{role}:{trace['stage_id']}:{position}","stage_id":trace["stage_id"],"repository":evidence["repository"],"path":evidence["path"],"sha256":evidence["sha256"],"start_line":evidence["start_line"],"end_line":evidence["end_line"],"excerpt_sha256":evidence["excerpt_sha256"],"reason":evidence["reason"]})
    if not choices: raise MappingEvidenceError(f"{role} trace has no evidence choices")
    return {"path":str(path),"sha256":observed,"artifact_sha256":ref["artifact_sha256"]},choices
