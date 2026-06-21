from __future__ import annotations

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "failed": {"retrying", "dead_letter"},
    "retrying": {"running", "cancelled"},
    # no "cancelled" key ⇒ terminal (no outgoing edges): never retried or reclaimed (B1).
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
