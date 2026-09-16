"""Require the proven value gate before the atom controller creates a run."""
import json
import importlib.util
import subprocess
import sys
from pathlib import Path
ADMISSION_FIELDS = ["packet", "receipt", "report"]

def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Value review file is missing or linked; supply the original regular file: " + str(path))
    return json.loads(path.read_text())

def admit(request, packet_path, receipt_path, root):
    if packet_path is None or receipt_path is None:
        raise ValueError("No value review supplied. Run atom-selection-gate assess for this exact request, then supply --value-packet and --value-receipt.")
    record = {"packet": read(packet_path), "receipt": read(receipt_path)}
    packet = record["packet"]
    if packet.get("schema_version") == "build-1":
        from build_admission import authorize
        authorize(packet, record["receipt"], Path(root))
        if packet["atom_request"] != request:
            raise ValueError("Approved build request differs from this request")
        record["report"] = {"status": "PASS", "text": "BUILD ADMISSION: PASS | approved exact atom; no priority judgment", "receipt_sha256": record["receipt"]["receipt_sha256"]}
        return record
    receipt = record["receipt"]
    if not isinstance(receipt, dict):
        raise ValueError("Value receipt must be the structured review output; run the gate again.")
    selection_path = packet.get("bindings", {}).get("selection")
    registered = {e["path"]: e for e in packet.get("evidence", [])}
    if not isinstance(selection_path, str) or selection_path not in registered:
        raise ValueError("No comparative selection bound to this request. Run selection_binding.py bind on an accepted selection, then obtain fresh value approval for its packet.")
    spec = importlib.util.spec_from_file_location("required_selection_binding", Path(__file__).with_name("selection_binding.py"))
    selection_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selection_module)
    bound_path = selection_module.local(Path(root).resolve(), selection_path)
    if selection_module.sha(bound_path) != registered[selection_path]["sha256"]:
        raise ValueError("Selection binding changed after proposal preparation; bind again and obtain fresh value approval.")
    selection_module.verify(read(bound_path), request, packet, root)
    gate = Path(__file__).resolve().parents[2] / "atom-selection-gate" / "gate.py"
    if gate.is_symlink() or not gate.is_file():
        raise ValueError("Required atom-selection-gate is missing; refresh the managed skills before starting work.")
    checked = subprocess.run([sys.executable, str(gate), "authorize", "--case", str(Path(packet_path).resolve()), "--receipt", str(Path(receipt_path).resolve()), "--source-root", str(root)], capture_output=True, text=True, timeout=30)
    if checked.returncode:
        raise ValueError(checked.stdout.strip() or checked.stderr.strip() or "Value authorization failed; inspect the review before starting work.")
    if packet.get("atom_request") != request:
        raise ValueError("The reviewed atom request differs from this request; include the exact atom_request in the packet and run a fresh review.")
    bindings = packet.get("bindings", {})
    sources = {e["path"] for e in packet["evidence"]}
    for field in ("goal", "state"):
        relative = bindings.get(field)
        if not isinstance(relative, str) or relative not in sources:
            raise ValueError("Current " + field + " needs a registered JSON source in packet bindings; review that source before starting work.")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or read(path) != packet[field]:
            raise ValueError("Current " + field + " differs from its reviewed binding; run a fresh review.")
    record["report"] = {"status": "PASS", "text": checked.stdout.strip(), "receipt_sha256": receipt["receipt_sha256"]}
    return record
