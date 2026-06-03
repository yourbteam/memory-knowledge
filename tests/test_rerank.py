from memory_knowledge.workflows.retrieval import rerank_results

K = 60  # RRF constant used by rerank_results


def test_empty_inputs():
    assert rerank_results([], []) == []


def test_pg_only():
    pg = [{"entity_key": "aaa", "rank": 0.8}]
    ranked = rerank_results(pg, [])
    assert len(ranked) == 1
    assert ranked[0]["entity_key"] == "aaa"
    assert ranked[0]["source"] == "postgres"
    assert abs(ranked[0]["combined_score"] - K / (K + 0)) < 1e-9  # top rank -> 1.0


def test_qdrant_only():
    qd = [{"entity_key": "bbb", "score": 0.7, "payload": {}}]
    ranked = rerank_results([], qd)
    assert len(ranked) == 1
    assert ranked[0]["entity_key"] == "bbb"
    assert ranked[0]["source"] == "qdrant"
    assert abs(ranked[0]["combined_score"] - 1.0) < 1e-9


def test_merge_same_entity():
    pg = [{"entity_key": "aaa", "rank": 0.5}]
    qd = [{"entity_key": "aaa", "score": 0.9, "payload": {}}]
    ranked = rerank_results(pg, qd)
    assert len(ranked) == 1
    assert ranked[0]["source"] == "both"
    # rank 0 in both sources -> 1.0 + 1.0
    assert abs(ranked[0]["combined_score"] - 2.0) < 1e-9


def test_sort_descending():
    pg = [
        {"entity_key": "low", "rank": 0.1},
        {"entity_key": "high", "rank": 0.9},
    ]
    ranked = rerank_results(pg, [])
    assert ranked[0]["entity_key"] == "high"
    assert ranked[1]["entity_key"] == "low"


def test_graph_boost():
    pg = [{"entity_key": "aaa", "rank": 0.5}]
    qd = [{"entity_key": "bbb", "score": 0.5, "payload": {}}]
    no_graph = rerank_results(pg, qd)
    with_graph = rerank_results(pg, qd, graph_entity_keys=["aaa"])

    aaa_no = next(r for r in no_graph if r["entity_key"] == "aaa")
    aaa_with = next(r for r in with_graph if r["entity_key"] == "aaa")
    # an already-retrieved entity gets the +0.1 graph bonus
    assert abs(aaa_with["combined_score"] - (aaa_no["combined_score"] + 0.1)) < 1e-9


def test_graph_only_discovery_bonus():
    ranked = rerank_results([], [], graph_entity_keys=["g"])
    assert ranked[0]["entity_key"] == "g"
    assert ranked[0]["source"] == "graph"
    assert abs(ranked[0]["combined_score"] - 0.3) < 1e-9


def test_rank_position_fusion():
    # fused by rank POSITION, not raw score magnitude
    pg = [
        {"entity_key": "a", "rank": 1.0},
        {"entity_key": "b", "rank": 0.5},
        {"entity_key": "c", "rank": 0.25},
    ]
    ranked = rerank_results(pg, [])
    assert [r["entity_key"] for r in ranked] == ["a", "b", "c"]
    by = {r["entity_key"]: r["combined_score"] for r in ranked}
    assert abs(by["a"] - K / (K + 0)) < 1e-9
    assert abs(by["b"] - K / (K + 1)) < 1e-9
    assert abs(by["c"] - K / (K + 2)) < 1e-9


def test_summary_weighted():
    # summary sources contribute at 0.8x
    ranked = rerank_results([], [], summary_qdrant_results=[{"entity_key": "s", "score": 0.5}])
    assert ranked[0]["source"] == "summary"
    assert abs(ranked[0]["combined_score"] - 0.8) < 1e-9
