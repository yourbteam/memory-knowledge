STRATEGY = "refuse-at-write"


class Register:
    """Every route out of the register checks completeness first. No partial read is possible."""

    def __init__(self, pieces):
        self._pieces = {p["id"]: p for p in pieces}
        self._answers = {}

    def answer(self, piece_id, value):
        self._answers[piece_id] = value

    def _unanswered(self):
        return [i for i in self._pieces if i not in self._answers]

    def _guard(self, what):
        missing = self._unanswered()
        if missing:
            raise Incomplete(f"cannot {what}: {len(missing)} piece(s) unanswered: {', '.join(sorted(missing))}")

    # route 1 — the report
    def report(self):
        self._guard("report")
        return {"answered": len(self._answers)}

    # route 2 — one piece
    def answer_for(self, piece_id):
        self._guard("read one answer")
        return self._answers[piece_id]

    # route 3 — iterate
    def all_answers(self):
        self._guard("list answers")
        return dict(self._answers)

    # route 4 — the stored state
    def dump(self, path):
        self._guard("write the register out")
        Path(path).write_text(json.dumps(self._answers))
        return path
