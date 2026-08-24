"""Deterministic alignment-unit input for mapping questions."""
from __future__ import annotations
import hashlib,json
from pathlib import Path

class MappingUnitError(RuntimeError): pass
def load_units(ref):
    if type(ref) is not dict or set(ref)!={"path","sha256","artifact_sha256"}: raise MappingUnitError("units reference fields changed")
    path=Path(ref.get("path",""))
    if not path.is_absolute() or path.is_symlink() or not path.is_file(): raise MappingUnitError("units path must be an absolute regular file")
    observed=hashlib.sha256(path.read_bytes()).hexdigest()
    if observed!=ref["sha256"]: raise MappingUnitError("units bytes changed")
    value=json.loads(path.read_text())
    if value.get("artifact_type")!="system-alignment-assessment-units" or value.get("artifact_sha256")!=ref["artifact_sha256"] or value.get("status")!="units-admitted": raise MappingUnitError("units identity or status changed")
    units=value.get("units")
    if type(units) is not list or not units or [u.get("sequence") for u in units]!=list(range(1,len(units)+1)) or len({u.get("unit_id") for u in units})!=len(units): raise MappingUnitError("units coverage, identity, or order changed")
    return {"path":str(path),"sha256":observed,"artifact_sha256":ref["artifact_sha256"]},units
