"""Assemble one exact annotation-and-code evidence packet per formula claim."""

from __future__ import annotations

from reporting_v3_column_index import _canonical, _sha


def _index(
    items: object, identity_field: str, label: str
) -> dict[str, dict[str, object]]:
    if not isinstance(items, list):
        raise ValueError(f"{label} must be a list")
    result: dict[str, dict[str, object]] = {}
    for position, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(
            item.get(identity_field), str
        ):
            raise ValueError(
                f"{label} item {position} has no valid {identity_field!r}"
            )
        identity = str(item[identity_field])
        if identity in result:
            raise ValueError(f"{label} repeats identity {identity!r}")
        result[identity] = item
    return result


def assemble(
    inventory: dict[str, object],
    bindings: dict[str, object],
    provenance: dict[str, object],
) -> list[dict[str, object]]:
    """Reconcile all three artifacts and return packets in claim order."""

    claims = inventory.get("claims")
    claim_index = _index(claims, "id", "claims")
    binding_index = _index(bindings.get("bindings"), "claim_id", "claim bindings")
    missing = sorted(set(claim_index) - set(binding_index))
    unknown = sorted(set(binding_index) - set(claim_index))
    if missing or unknown:
        raise ValueError(
            f"claim binding coverage differs: missing={missing}, unknown={unknown}"
        )
    code_index = _index(
        provenance.get("columns"), "excel_column", "provenance columns"
    )
    packets: list[dict[str, object]] = []
    assert isinstance(claims, list)
    for claim in claims:
        assert isinstance(claim, dict)
        claim_id = str(claim["id"])
        binding = binding_index[claim_id]
        references = binding.get("referenced_columns")
        if not isinstance(references, list):
            raise ValueError(f"claim {claim_id!r} has no referenced-column list")
        evidence: list[dict[str, object]] = []
        for position, reference in enumerate(references):
            if not isinstance(reference, dict) or not isinstance(
                reference.get("excel_column"), str
            ):
                raise ValueError(
                    f"claim {claim_id!r} reference {position} has no Excel-column identity"
                )
            column = str(reference["excel_column"])
            if column not in code_index:
                raise ValueError(
                    f"claim {claim_id!r} references unproven column {column!r}"
                )
            code = code_index[column]
            if (
                reference.get("column_record_sha256")
                != code.get("column_record_sha256")
            ):
                raise ValueError(
                    f"claim {claim_id!r} column {column!r} changed between binding and provenance"
                )
            evidence.append(code)
        packet = {
            "claim": claim,
            "claim_sha256": _sha(_canonical(claim)),
            "binding": binding,
            "binding_sha256": _sha(_canonical(binding)),
            "column_evidence": evidence,
            "evidence_status": (
                "code_evidence_bound" if evidence else "no_explicit_column_evidence"
            ),
        }
        packet["packet_sha256"] = _sha(_canonical(packet))
        packets.append(packet)
    return packets
