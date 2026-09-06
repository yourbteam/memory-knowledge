"""Code-owned receipts for complete reader input; never certify semantic correctness."""
import hashlib
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("coverage_reflow", Path(__file__).parent / "reflow.py")
reflow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reflow)

COVERAGE_FIELDS = {"coverage"}
POLICY = "complete-reader-input-v1"
CONTRACT = {"coverage": {"policy": "pinned-string", "batches": "list", "complete": "enum"}}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def text_batches(text, limit=6000):
    """Lossless ranges on whole sentence boundaries; indivisible long sentences stay whole."""
    ends = [match.end() for match in reflow.SENTENCE_END.finditer(text)]
    if not ends or ends[-1] != len(text):
        ends.append(len(text))
    rows, start = [], 0
    while start < len(text):
        within = [end for end in ends if start < end <= start + limit]
        end = max(within) if within else next(end for end in ends if end > start)
        rows.append({"start": start, "end": end, "text": text[start:end]})
        start = end
    return rows or [{"start": 0, "end": 0, "text": ""}]


def unit_batches(units, limit=9000):
    """Whole units retain global identities; oversized units travel alone and intact."""
    batches, batch, size = [], [], 0
    for index, unit in enumerate(units, 1):
        line = f"{index}. {unit}"
        if batch and size + len(line) + 1 > limit:
            batches.append(batch)
            batch, size = [], 0
        batch.append({"id": index, "text": unit, "line": line})
        size += len(line) + 1
    if batch:
        batches.append(batch)
    return batches


def receipt(source, target, batches, complete=True):
    return {"policy": POLICY, "source_sha256": digest(source),
            "target_sha256": digest(target), "batches": batches, "complete": complete}


def matches(value, source, target):
    """Recompute offered boundaries from source instead of trusting a completion flag."""
    if not (isinstance(value, dict) and value.get("policy") == POLICY
            and value.get("source_sha256") == digest(source)
            and value.get("target_sha256") == digest(target)
            and value.get("complete") is True):
        return False
    batches = value.get("batches")
    if not isinstance(batches, list):
        return False
    if batches and "cut" in batches[0]:
        if [row.get("cut") for row in batches] != list(reflow.CUTS):
            return False
        for row in batches:
            if not _matches_units(row, reflow.CUTS[row["cut"]](source, 1), source, target):
                return False
        return True
    expected = text_batches("\n".join(reflow.units(source, min_chars=1)))
    return (len(batches) == len(expected) and all(
        row.get("start") == batch["start"] and row.get("end") == batch["end"]
        and row.get("shown_sha256") == digest(batch["text"])
        and row.get("answer") in ("YES", "NO")
        for row, batch in zip(batches, expected)))


def _matches_units(value, units, source, target):
    if (value.get("policy") != POLICY or value.get("source_sha256") != digest(source)
            or value.get("target_sha256") != digest(target) or value.get("complete") is not True):
        return False
    actual = value.get("batches", [])
    expected = unit_batches(units)
    return len(actual) == len(expected) and all(
        row.get("unit_ids") == [unit["id"] for unit in batch]
        and row.get("shown_sha256") == digest("\n".join(unit["line"] for unit in batch))
        for row, batch in zip(actual, expected))
