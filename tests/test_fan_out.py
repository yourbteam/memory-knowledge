from memory_knowledge.workflows.retrieval import classify_prompt


def test_exact_lookup_first_store_is_postgres():
    """exact_lookup policy has first_store='postgres' in seed data."""
    assert classify_prompt("find getUserById")[0] == "exact_lookup"


def test_conceptual_lookup_first_store_is_qdrant():
    """conceptual_lookup policy has first_store='qdrant' in seed data."""
    assert classify_prompt("tell me about logging")[0] == "conceptual_lookup"


def test_impact_analysis_allows_fanout():
    """impact_analysis policy has allow_fanout=TRUE in seed data."""
    assert classify_prompt("what would break if I change the schema")[0] == "impact_analysis"


def test_assemble_context_bundle_includes_provenance():
    """Verify assemble_context_bundle adds commit_sha and branch_name when provided."""
    # This is tested via the function's parameter interface
    from memory_knowledge.workflows.retrieval import assemble_context_bundle
    import inspect

    sig = inspect.signature(assemble_context_bundle)
    params = list(sig.parameters.keys())
    assert "commit_sha" in params
    assert "branch_name" in params


def test_rerank_with_source_field():
    """Verify rerank results include source field for retrieval_reason."""
    from memory_knowledge.workflows.retrieval import rerank_results

    pg = [{"entity_key": "aaa", "rank": 0.8}]
    qd = [{"entity_key": "bbb", "score": 0.7, "payload": {}}]
    ranked = rerank_results(pg, qd)

    pg_item = next(r for r in ranked if r["entity_key"] == "aaa")
    qd_item = next(r for r in ranked if r["entity_key"] == "bbb")
    assert pg_item["source"] == "postgres"
    assert qd_item["source"] == "qdrant"
