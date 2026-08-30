

def main():
    variant = os.environ["EXPERIMENT_VARIANT_ID"]
    src = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    tel = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    seq = 0
    telemetry(tel, variant, seq := seq + 1, "start", strategy=STRATEGY,
              input_sha256=hashlib.sha256(src.read_bytes()).hexdigest())

    text = subprocess.run(["pdftotext", "-layout", str(src), "-"],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    pieces = split(text)
    norm = lambda s: re.sub(r"\s+", "", s)
    if norm("".join(pieces)) != norm(text):
        result_path.write_text(json.dumps({"schema_version": 1, "variant_id": variant,
            "status": "failed", "outcome": {}, "metrics": {},
            "error": STRATEGY + " does not preserve the document"}))
        telemetry(tel, variant, seq + 1, "refused", reason="document not preserved")
        return 1
    telemetry(tel, variant, seq := seq + 1, "split", pieces=len(pieces))

    retained, detail = [], []
    for anchor in anchors_with_context(text):
        holder = next((p for p in pieces if anchor["line"] in p), None)
        if holder is None:
            retained.append(0.0)
            detail.append({"anchor": anchor["line"][:70], "kept": 0, "of": len(anchor["neighbourhood"]),
                           "note": "anchor line itself split across pieces"})
            continue
        kept = sum(1 for l in anchor["neighbourhood"] if l in holder)
        share = kept / len(anchor["neighbourhood"])
        retained.append(share)
        detail.append({"anchor": anchor["line"][:70], "kept": kept, "of": len(anchor["neighbourhood"])})
        telemetry(tel, variant, seq := seq + 1, "anchor measured",
                  anchor=anchor["line"][:60], kept=kept, of=len(anchor["neighbourhood"]))

    score = sum(retained) / len(retained) if retained else 0.0
    metrics = {"context-retention": score, "piece-count": float(len(pieces))}
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": variant,
        "status": "completed", "outcome": {"strategy": STRATEGY, "anchors": detail},
        "metrics": metrics, "error": None}))
    telemetry(tel, variant, seq + 1, "finish", **metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
