"""Register: refuse-at-write."""
import json
import time
from pathlib import Path

STRATEGY = "refuse-at-write"


class Incomplete(Exception):
    pass


class Register:
    """Every route out of the register checks completeness first. No partial read is possible."""

    def __init__(self, pieces):
        self._pieces = {p["id"]: p for p in pieces}
        self._answers = {}

    def answer(self, piece_id, value, by="unnamed reader"):
        self._answers[piece_id] = {"what": value, "by": by, "at": time.time()}

    def _unanswered(self):
        return [i for i in self._pieces if i not in self._answers]

    def _guard(self, what):
        missing = sorted(self._unanswered())
        if missing:
            shown = ", ".join(missing[:10])
            more = "" if len(missing) <= 10 else f", and {len(missing) - 10} more"
            raise Incomplete(
                f"cannot {what}: {len(missing)} of {len(self._pieces)} piece(s) unanswered: "
                f"{shown}{more}. Answer them with `cover.py answer --piece <id> --by <who> "
                f"--what <what it says>`, or run `cover.py status` to list them all."
            )


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
