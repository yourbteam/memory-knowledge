"""Compare ways of deciding which obligations carry a check a finished brief could fail.

The anchors are taken from the page, not from an earlier ask. Six lines a finished brief either
satisfies or does not — the two that say a brief cannot be approved without baseline, target,
source and owner, and page 82's four rows naming the nine fields to record for every KPI. Three
lines that state nothing a brief could fail — two fragments of a table row, and one naming who owns
the brief. An approach that drops the first six, or keeps the three, has not done the job whatever
else it scores.
"""
import hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = 2   # the same material twice, because the whole point is whether the answer holds still


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


approach = _load("approach")
_iv = _load("interview")


class Interview:
    def ask_free(self, reader, prompt):
        if not reader:
            return ""
        out = subprocess.run(reader.split(), input=prompt.encode(), capture_output=True)
        return out.stdout.decode("utf-8", "replace").strip()

    ask_choice = staticmethod(_iv.ask_choice)
    _candidates = staticmethod(_iv._candidates)


def telemetry(path, variant, seq, event, **fields):
    with open(path, "a") as fh:
        fh.write(json.dumps({"variant": variant, "seq": seq, "at": time.time(),
                             "event": event, **fields}) + "\n")


def main():
    variant = os.environ["EXPERIMENT_VARIANT_ID"]
    src = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    tel = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    reader = os.environ.get("PIECE_READER_COMMAND")
    material = json.loads(src.read_text())
    lines, must_keep, must_drop = material["lines"], set(material["must_keep"]), set(material["must_drop"])
    telemetry(tel, variant, 1, "start", strategy=approach.STRATEGY,
              input_sha256=hashlib.sha256(src.read_bytes()).hexdigest(), lines=len(lines))

    iv, runs, detail = Interview(), [], []
    for r in range(RUNS):
        kept, extra = approach.choose(lines, reader, iv)
        runs.append(set(kept)); detail.append(extra)
        telemetry(tel, variant, 2 + r, "run", index=r + 1, kept=sorted(kept))

    first = runs[0]
    dropped_anchor = sorted(must_keep - first)
    kept_unfalsifiable = sorted(must_drop & first)
    unstable = sorted(runs[0] ^ runs[1]) if len(runs) > 1 else []
    contested = [n for n in range(1, len(lines) + 1) if n not in must_keep and n not in must_drop]
    decided = [n for n in contested if (n in runs[0]) == (n in runs[1])]

    metrics = {"drops-an-anchor": float(len(dropped_anchor)),
               "keeps-the-unfalsifiable": float(len(kept_unfalsifiable)),
               "unstable-lines": float(len(unstable)),
               "settles-the-contested": round(len(decided) / len(contested), 3) if contested else 0.0}
    result_path.write_text(json.dumps({
        "schema_version": 1, "variant_id": variant, "status": "completed",
        "outcome": {"strategy": approach.STRATEGY, "kept": sorted(first), "runs": [sorted(r) for r in runs],
                    "dropped_anchor": dropped_anchor, "kept_unfalsifiable": kept_unfalsifiable,
                    "unstable_lines": unstable, "detail": detail},
        "metrics": metrics, "error": None}))
    telemetry(tel, variant, 2 + RUNS, "finish", **metrics)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        Path(os.environ["EXPERIMENT_RESULT_PATH"]).write_text(json.dumps({
            "schema_version": 1, "variant_id": os.environ.get("EXPERIMENT_VARIANT_ID"),
            "status": "failed", "outcome": {}, "metrics": {},
            "error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
