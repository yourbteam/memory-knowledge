from scripts.blocker_catalog import fingerprint, normalize_error_signature


def test_fingerprint_normalizes_volatile_values_but_keeps_error_code():
    first = fingerprint(
        "deploy", "lineage", "upload",
        "ERR42 at 2026-01-01T12:00:00Z id 123e4567-e89b-12d3-a456-426614174000 attempt 1",
    )
    second = fingerprint(
        "deploy", "lineage", "upload",
        "ERR42 at 2027-02-02T13:00:00Z id 223e4567-e89b-12d3-a456-426614174999 attempt 9",
    )
    different = fingerprint("deploy", "lineage", "upload", "ERR43 attempt 9")
    assert first == second and first != different
    assert "err42" in normalize_error_signature("ERR42 line 99")
