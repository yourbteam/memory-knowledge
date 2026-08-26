"""Compare ways of finding which entries state the same obligation.

The 28 entries are the definitive atom-4 run's real output. Two verified kinds of repeat: three
pairs sharing a statement of 41-195 characters verbatim, and three pairs stating the same rule in
different words — which no substring can see. Five verified pairs state different obligations and
must never merge: merging two distinct requirements loses one, which is why wrongly-merged ranks
above every miss. The same material is run twice, because a dedupe that answers differently twice
is not a rule.
"""
import hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = 2


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


approach = _load("approach")


class Interview:
    calls = 0

    def ask_free(self, reader, prompt):
        if not reader:
            return ""
        Interview.calls += 1
        out = subprocess.run(reader.split(), input=prompt.encode(), capture_output=True)
        return out.stdout.decode("utf-8", "replace").strip()


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
    entries = [e["text"] for e in material["entries"]]
    verbatim = {tuple(sorted(p)) for p in material.get("must_merge_verbatim", [])}
    semantic = {tuple(sorted(p)) for p in material.get("must_merge_semantic", [])}
    apart = {tuple(sorted(p)) for p in material.get("must_stay_apart", [])}
    telemetry(tel, variant, 1, "start", strategy=approach.STRATEGY,
              input_sha256=hashlib.sha256(src.read_bytes()).hexdigest(), entries=len(entries))

    iv, runs, details = Interview(), [], []
    for i in range(RUNS):
        pairs, detail = approach.choose(entries, reader, iv)
        runs.append({tuple(sorted(p)) for p in pairs}); details.append(detail)
        telemetry(tel, variant, 2 + i, "run", index=i + 1, merged_pairs=sorted(map(list, runs[-1])))
    first = runs[0]

    metrics = {"apart-pairs-merged": float(len(apart & first)),
               "verbatim-pairs-missed": float(len(verbatim - first)),
               "semantic-pairs-missed": float(len(semantic - first)),
               "unstable-pairs": float(len(runs[0] ^ runs[1])) if len(runs) > 1 else 0.0,
               "reader-calls": float(Interview.calls)}
    result_path.write_text(json.dumps({
        "schema_version": 1, "variant_id": variant, "status": "completed",
        "outcome": {"strategy": approach.STRATEGY,
                    "merged_pairs": sorted(map(list, first)),
                    "runs": [sorted(map(list, s)) for s in runs],
                    "missed_verbatim": sorted(map(list, verbatim - first)),
                    "missed_semantic": sorted(map(list, semantic - first)),
                    "wrongly_merged": sorted(map(list, apart & first)),
                    "detail": details},
        "metrics": metrics, "error": None}, ensure_ascii=False))
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
