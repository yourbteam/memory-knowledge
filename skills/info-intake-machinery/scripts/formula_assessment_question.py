"""Render exactly one code-controlled formula assessment question."""

from __future__ import annotations


VERDICTS = ["confirmed", "contradicted", "unresolved"]


def render_question(
    packets: list[object], position: int, shared_code_evidence: list[object] | None = None
) -> dict[str, object]:
    if not isinstance(position, int) or position < 0 or position >= len(packets):
        raise ValueError(
            f"question position {position!r} is outside 0..{len(packets) - 1}"
        )
    packet = packets[position]
    if not isinstance(packet, dict):
        raise ValueError(f"assessment packet {position} is not an object")
    claim = packet.get("claim")
    packet_sha256 = packet.get("packet_sha256")
    if (
        not isinstance(claim, dict)
        or not isinstance(claim.get("id"), str)
        or not isinstance(packet_sha256, str)
        or len(packet_sha256) != 64
    ):
        raise ValueError(f"assessment packet {position} has invalid immutable identity")
    evidence: list[dict[str, object]] = [
        {"id": "claim", "kind": "claim", "value": claim.get("statement")},
        {"id": "origin", "kind": "visual_origin", "value": claim.get("origin")},
        {"id": "target", "kind": "visual_target", "value": claim.get("target")},
        {
            "id": "relationship",
            "kind": "visual_relationship",
            "value": {
                "id": claim.get("relationship_id"),
                "sha256": claim.get("relationship_sha256"),
            },
        },
    ]
    columns = packet.get("column_evidence")
    if not isinstance(columns, list):
        raise ValueError(f"assessment packet {position} has no column-evidence list")
    for column in columns:
        if not isinstance(column, dict) or not isinstance(
            column.get("excel_column"), str
        ):
            raise ValueError(
                f"assessment packet {position} has invalid column evidence"
            )
        identity = str(column["excel_column"])
        evidence.append(
            {
                "id": f"column:{identity}:writer",
                "kind": "spreadsheet_writer",
                "value": {
                    "root": column.get("root"),
                    "writer_line_number": column.get("writer_line_number"),
                    "column_record_sha256": column.get("column_record_sha256"),
                },
            }
        )
        spans = column.get("provenance_spans")
        if not isinstance(spans, list):
            raise ValueError(f"column {identity!r} has no provenance-span list")
        for number, span in enumerate(spans, start=1):
            evidence.append(
                {
                    "id": f"column:{identity}:provenance:{number}",
                    "kind": "calculation_provenance",
                    "value": span,
                }
            )
    for column in shared_code_evidence or []:
        if not isinstance(column, dict) or not isinstance(
            column.get("excel_column"), str
        ):
            raise ValueError("shared code evidence has invalid column identity")
        identity = str(column["excel_column"])
        evidence.append(
            {
                "id": f"shared-column:{identity}:writer",
                "kind": "shared_spreadsheet_writer",
                "value": {
                    "column_record": column.get("column_record"),
                    "root": column.get("root"),
                    "writer_line_number": column.get("writer_line_number"),
                },
            }
        )
        spans = column.get("provenance_spans")
        if not isinstance(spans, list):
            raise ValueError(f"shared column {identity!r} has no provenance spans")
        for number, span in enumerate(spans, start=1):
            evidence.append(
                {
                    "id": f"shared-column:{identity}:provenance:{number}",
                    "kind": "shared_calculation_provenance",
                    "value": span,
                }
            )
    return {
        "schema_version": 1,
        "question_id": f"assessment-{position + 1:06d}",
        "position": position + 1,
        "claim_id": claim["id"],
        "packet_sha256": packet_sha256,
        "prompt": (
            "Judge the whole claim only from the presented evidence. Choose confirmed "
            "only when every part is supported, contradicted only when evidence disproves "
            "at least one part, and unresolved when evidence is insufficient."
        ),
        "allowed_verdicts": VERDICTS,
        "evidence_catalog": evidence,
    }
