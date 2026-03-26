from __future__ import annotations

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running", "cancelled"},
    "running": {"completed", "failed"},
    "failed": {"retrying", "dead_letter"},
    "retrying": {"running"},
}


class InvalidStateTransition(Exception):
    def __init__(self, current: str, requested: str):
        super().__init__(f"Invalid state transition: {current} -> {requested}")
        self.current = current
        self.requested = requested


def validate_transition(current_state: str, new_state: str) -> None:
    """Raise InvalidStateTransition if the transition is not allowed."""
    allowed = VALID_TRANSITIONS.get(current_state, set())
    if new_state not in allowed:
        raise InvalidStateTransition(current_state, new_state)
