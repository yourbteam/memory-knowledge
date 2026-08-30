"""Replayable, integrity-bound evidence for one three-seat checkability decision."""
from __future__ import annotations

import hashlib
import json
import re


SCHEMA_VERSION = 1


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def parse_reply(raw, item_count):
    picked, validation = set(), []
    for line_number, line in enumerate(raw.split("\n"), 1):
        match = re.match(r"^\s*(\d{1,3})\s*[.):]?\s*$", line)
        number = int(match.group(1)) if match else None
        accepted = number is not None and 1 <= number <= item_count
        if accepted:
            picked.add(number)
        validation.append({
            "line": line_number, "text": line, "accepted": accepted,
            "number": number,
            "reason": "accepted" if accepted else ("out-of-range" if number is not None else "malformed"),
        })
    return sorted(picked), validation


def parse_choice(raw, choices=("YES", "NO")):
    """Apply the same standalone-line choice contract as the reader boundary."""
    for line in raw.split("\n"):
        candidate = line.strip().strip('"').rstrip(".").upper()
        for choice in choices:
            if candidate == choice.upper():
                return choice
    return None


def build(raw_replies, item_texts, target, prompt):
    seats = []
    for seat, raw in enumerate(raw_replies, 1):
        parsed, validation = parse_reply(raw, len(item_texts))
        seats.append({"seat": seat, "raw_reply": raw, "parsed_selections": parsed,
                      "validation": validation})
    aggregate = []
    for item in range(1, len(item_texts) + 1):
        votes = sum(item in seat["parsed_selections"] for seat in seats)
        disposition = "keep" if votes == 3 else ("drop" if votes == 0 else "owner")
        aggregate.append({"item": item, "votes": votes, "disposition": disposition})
    record = {
        "schema_version": SCHEMA_VERSION,
        "target": target, "target_sha256": hashlib.sha256(target.encode()).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "items_sha256": _digest(item_texts), "item_count": len(item_texts),
        "seats": seats, "aggregate": aggregate,
    }
    record["record_sha256"] = _digest(record)
    return record


def build_binary(raw_attempts_by_seat, item_text, target, prompt):
    """Build the same integrity envelope for one YES/NO split-child decision.

    Choice asks can retry malformed replies, so every raw attempt is retained and independently
    parsed. A missing valid choice is not silently counted as NO; it remains owner-visible doubt.
    """
    if len(raw_attempts_by_seat) != 3:
        raise ValueError("binary checkability requires exactly three seats")
    seats = []
    for seat, raw_attempts in enumerate(raw_attempts_by_seat, 1):
        if not isinstance(raw_attempts, list) or not raw_attempts:
            raise ValueError(f"binary checkability seat {seat} has no raw attempts")
        validation, final = [], None
        for attempt, raw in enumerate(raw_attempts, 1):
            if not isinstance(raw, str):
                raise ValueError(f"binary checkability seat {seat} attempt {attempt} is not text")
            parsed = parse_choice(raw)
            validation.append({
                "attempt": attempt,
                "raw_reply": raw,
                "accepted": parsed is not None,
                "choice": parsed,
                "reason": "accepted" if parsed is not None else "malformed",
            })
            if parsed is not None:
                final = parsed
                if attempt != len(raw_attempts):
                    raise ValueError(f"binary checkability seat {seat} continued after acceptance")
        seats.append({
            "seat": seat,
            "raw_replies": list(raw_attempts),
            "parsed_selections": [1] if final == "YES" else [],
            "parsed_choice": final,
            "validation": validation,
        })
    yes_votes = sum(seat["parsed_choice"] == "YES" for seat in seats)
    no_votes = sum(seat["parsed_choice"] == "NO" for seat in seats)
    invalid_seats = [seat["seat"] for seat in seats if seat["parsed_choice"] is None]
    disposition = "keep" if yes_votes == 3 else ("drop" if no_votes == 3 else "owner")
    record = {
        "schema_version": SCHEMA_VERSION,
        "mode": "binary-choice",
        "target": target,
        "target_sha256": hashlib.sha256(target.encode()).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "items_sha256": _digest([item_text]),
        "item_count": 1,
        "seats": seats,
        "aggregate": [{
            "item": 1,
            "votes": yes_votes,
            "no_votes": no_votes,
            "invalid_seats": invalid_seats,
            "disposition": disposition,
        }],
    }
    record["record_sha256"] = _digest(record)
    return record


def _require_exact_object(value, expected_keys, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be one object")
    if set(value) != set(expected_keys):
        raise ValueError(f"{label} has the wrong fields")


def _validate_binary_shape(record):
    """Reject malformed persisted JSON as evidence, never as a programming exception."""
    _require_exact_object(record, {
        "schema_version", "mode", "target", "target_sha256", "prompt_sha256",
        "items_sha256", "item_count", "seats", "aggregate", "record_sha256",
    }, "binary checkability record")
    if type(record["schema_version"]) is not int or record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("binary checkability schema version is invalid")
    if record["mode"] != "binary-choice":
        raise ValueError("binary checkability mode is invalid")
    if not isinstance(record["target"], str):
        raise ValueError("binary checkability target must be text")
    for field in ("target_sha256", "prompt_sha256", "items_sha256", "record_sha256"):
        value = record[field]
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"binary checkability {field} must be one SHA-256")
    if type(record["item_count"]) is not int or record["item_count"] != 1:
        raise ValueError("binary checkability item_count must be 1")
    seats = record["seats"]
    if not isinstance(seats, list) or len(seats) != 3:
        raise ValueError("binary checkability requires exactly three persisted seats")
    for seat_number, seat in enumerate(seats, 1):
        label = f"binary checkability seat {seat_number}"
        _require_exact_object(seat, {
            "seat", "raw_replies", "parsed_selections", "parsed_choice", "validation",
        }, label)
        if type(seat["seat"]) is not int or seat["seat"] != seat_number:
            raise ValueError(f"{label} identity is invalid")
        raw_replies = seat["raw_replies"]
        if (not isinstance(raw_replies, list) or not raw_replies
                or any(not isinstance(raw, str) for raw in raw_replies)):
            raise ValueError(f"{label} raw_replies must be a nonempty text list")
        selections = seat["parsed_selections"]
        if not isinstance(selections, list) or any(type(item) is not int for item in selections):
            raise ValueError(f"{label} parsed selections must be an integer list")
        parsed_choice = seat["parsed_choice"]
        if parsed_choice is not None and (
                not isinstance(parsed_choice, str) or parsed_choice not in {"YES", "NO"}):
            raise ValueError(f"{label} parsed choice is invalid")
        validation = seat["validation"]
        if not isinstance(validation, list) or len(validation) != len(raw_replies):
            raise ValueError(f"{label} validation must cover every raw reply")
        for attempt_number, attempt in enumerate(validation, 1):
            attempt_label = f"{label} validation {attempt_number}"
            _require_exact_object(attempt, {
                "attempt", "raw_reply", "accepted", "choice", "reason",
            }, attempt_label)
            if type(attempt["attempt"]) is not int or attempt["attempt"] != attempt_number:
                raise ValueError(f"{attempt_label} identity is invalid")
            if not isinstance(attempt["raw_reply"], str):
                raise ValueError(f"{attempt_label} raw reply must be text")
            if type(attempt["accepted"]) is not bool:
                raise ValueError(f"{attempt_label} accepted flag must be boolean")
            choice = attempt["choice"]
            if choice is not None and (
                    not isinstance(choice, str) or choice not in {"YES", "NO"}):
                raise ValueError(f"{attempt_label} choice is invalid")
            if attempt["reason"] not in {"accepted", "malformed"}:
                raise ValueError(f"{attempt_label} reason is invalid")
    aggregate = record["aggregate"]
    if not isinstance(aggregate, list) or len(aggregate) != 1:
        raise ValueError("binary checkability aggregate must contain exactly one item")
    decision = aggregate[0]
    _require_exact_object(decision, {
        "item", "votes", "no_votes", "invalid_seats", "disposition",
    }, "binary checkability aggregate item")
    for field in ("item", "votes", "no_votes"):
        if type(decision[field]) is not int:
            raise ValueError(f"binary checkability aggregate {field} must be an integer")
    if (not isinstance(decision["invalid_seats"], list)
            or any(type(seat) is not int for seat in decision["invalid_seats"])):
        raise ValueError("binary checkability invalid_seats must be an integer list")
    if (not isinstance(decision["disposition"], str)
            or decision["disposition"] not in {"keep", "drop", "owner"}):
        raise ValueError("binary checkability disposition is invalid")


def validate(record, item_texts, target, prompt):
    expected_hash = record.get("record_sha256")
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    if expected_hash != _digest(body):
        raise ValueError("checkability record integrity mismatch")
    rebuilt = build([seat["raw_reply"] for seat in record["seats"]], item_texts, target, prompt)
    if rebuilt != record:
        raise ValueError("checkability record cannot be replayed to its persisted disposition")
    return record


def validate_binary(record, item_text, target, prompt):
    _validate_binary_shape(record)
    expected_hash = record.get("record_sha256")
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    if expected_hash != _digest(body):
        raise ValueError("checkability record integrity mismatch")
    rebuilt = build_binary(
        [seat["raw_replies"] for seat in record["seats"]], item_text, target, prompt
    )
    if rebuilt != record:
        raise ValueError("checkability record cannot be replayed to its persisted disposition")
    return record
