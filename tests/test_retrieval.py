from memory_knowledge.workflows.retrieval import filter_eligible_learned_rows


def rows():
    base = {"is_active": True, "evidence_resolution_errors": []}
    return [
        {**base, "title": "verified rule", "memory_type": "common_issue",
         "source_kind": "agent_proposal", "verification_status": "verified",
         "content_kind": None, "evidence_refs": None},
        {**base, "title": "confirmed note", "memory_type": "operator_note",
         "source_kind": "operator_note", "verification_status": "human_asserted",
         "content_kind": "root-cause", "evidence_refs": [{"kind": "revision"}]},
        {**base, "title": "candidate", "memory_type": "operator_note",
         "source_kind": "operator_note", "verification_status": "unverified",
         "content_kind": "root-cause", "evidence_refs": [{"kind": "revision"}]},
        {**base, "title": "legacy", "memory_type": "operator_note",
         "source_kind": "operator_note", "verification_status": "verified",
         "content_kind": None, "evidence_refs": None},
        {**base, "title": "inactive", "memory_type": "operator_note",
         "source_kind": "operator_note", "verification_status": "human_asserted",
         "content_kind": "repository-fact", "evidence_refs": [{"kind": "revision"}],
         "is_active": False},
    ]


def test_repo_scoped_retrieval_filters_every_ineligible_trust_tier():
    assert [row["title"] for row in filter_eligible_learned_rows(rows())] == [
        "verified rule", "confirmed note",
    ]
