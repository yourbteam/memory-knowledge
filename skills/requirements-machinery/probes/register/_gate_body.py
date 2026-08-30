STRATEGY = "gate-at-report"


class Register:
    """Answers are stored freely. Only the report call checks completeness."""

    def __init__(self, pieces):
        self._pieces = {p["id"]: p for p in pieces}
        self._answers = {}

    def answer(self, piece_id, value):
        self._answers[piece_id] = value

    def _unanswered(self):
        return [i for i in self._pieces if i not in self._answers]

    # route 1 — the report
    def report(self):
        missing = self._unanswered()
        if missing:
            raise Incomplete(f"cannot report: {len(missing)} piece(s) unanswered: {', '.join(sorted(missing))}")
        return {"answered": len(self._answers)}

    # route 2 — one piece
    def answer_for(self, piece_id):
        return self._answers[piece_id]

    # route 3 — iterate
    def all_answers(self):
        return dict(self._answers)

    # route 4 — the stored state
    def dump(self, path):
        Path(path).write_text(json.dumps(self._answers))
        return path
