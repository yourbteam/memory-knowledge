

def main():
    variant = os.environ["EXPERIMENT_VARIANT_ID"]
    src = Path(os.environ["EXPERIMENT_INPUT_PATH"])
    work = Path(os.environ["EXPERIMENT_WORK_DIR"])
    result_path = Path(os.environ["EXPERIMENT_RESULT_PATH"])
    tel = Path(os.environ["EXPERIMENT_TELEMETRY_PATH"])
    seq = 0
    telemetry(tel, variant, seq := seq + 1, "start", strategy=STRATEGY,
              input_sha256=hashlib.sha256(src.read_bytes()).hexdigest())

    pieces = pieces_of(src)
    reg = Register(pieces)
    # every piece answered but one, deliberately: this is the captured failure case
    hole = pieces[81]["id"] if len(pieces) > 81 else pieces[-1]["id"]
    for p in pieces:
        if p["id"] != hole:
            reg.answer(p["id"], "read")
    telemetry(tel, variant, seq := seq + 1, "register built", pieces=len(pieces), unanswered=hole)

    leaks, refusals = [], []
    routes = {
        "ask for the result": lambda: reg.report(),
        "ask about one answered piece": lambda: reg.answer_for(pieces[0]["id"]),
        "list everything answered": lambda: reg.all_answers(),
        "write the register out": lambda: reg.dump(work / "dump.json"),
    }
    for name, route in routes.items():
        try:
            route()
            leaks.append(name)
            telemetry(tel, variant, seq := seq + 1, "leak", route=name)
        except Incomplete as refusal:
            refusals.append(str(refusal))
            telemetry(tel, variant, seq := seq + 1, "refused", route=name, message=str(refusal)[:160])

    names_the_hole = 1.0 if refusals and all(hole in r for r in refusals) else 0.0

    # the captured success case: once the hole is filled, the result is produced
    reg.answer(hole, "read")
    try:
        completed = reg.report()
        telemetry(tel, variant, seq := seq + 1, "completed after filling the hole", **completed)
    except Incomplete as refusal:
        result_path.write_text(json.dumps({"schema_version": 1, "variant_id": variant,
            "status": "failed", "outcome": {}, "metrics": {},
            "error": "refused even with every piece answered: " + str(refusal)}))
        return 1

    metrics = {"names-the-hole": names_the_hole, "leak-count": float(len(leaks))}
    result_path.write_text(json.dumps({"schema_version": 1, "variant_id": variant,
        "status": "completed",
        "outcome": {"strategy": STRATEGY, "unanswered_piece": hole, "leaked_routes": leaks,
                    "refusal_messages": refusals},
        "metrics": metrics, "error": None}))
    telemetry(tel, variant, seq + 1, "finish", **metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
