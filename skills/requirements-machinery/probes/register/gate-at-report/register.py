"""Register: gate-at-report."""
import json
import time
from pathlib import Path

STRATEGY = "gate-at-report"


class Incomplete(Exception):
    pass


class Register:
    """Answers are stored freely. Only the report call checks completeness."""

    def __init__(self, pieces):
        self._pieces = {p["id"]: p for p in pieces}
        self._answers = {}

    def answer(self, piece_id, value, by="unnamed reader"):
        self._answers[piece_id] = {"what": value, "by": by, "at": time.time()}

    def _unanswered(self):
        return [i for i in self._pieces if i not in self._answers]


    def status(self):
        """Always readable, and deliberately so: it carries no answer, only whether there is one.

        Asking whether a piece was answered, and by whom, is how the hole is found. Gating that
        would leave the owner unable to see what is missing. What stays gated is the answer itself.
        """
        return {piece_id: ({"answered": True, "by": self._answers[piece_id]["by"],
                            "at": self._answers[piece_id]["at"]}
                           if piece_id in self._answers else {"answered": False})
                for piece_id in self._pieces}

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
