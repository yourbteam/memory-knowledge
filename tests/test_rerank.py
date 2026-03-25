from memory_knowledge.workflows.retrieval import rerank_results


def test_empty_inputs():
    assert rerank_results([], []) == []


def test_pg_only():
    pg = [{"entity_key": "aaa", "rank": 0.8}]
    ranked = rerank_results(pg, [])
    assert len(ranked) == 1
    assert ranked[0]["entity_key"] == "aaa"
    assert ranked[0]["pg_score"] == 1.0  # normalized: 0.8/0.8


def test_qdrant_only():
    qd = [{"entity_key": "bbb", "score": 0.7, "payload": {}}]
    ranked = rerank_results([], qd)
    assert len(ranked) == 1
    assert ranked[0]["entity_key"] == "bbb"
    assert ranked[0]["qdrant_score"] == 0.7


def test_merge_same_entity():
    pg = [{"entity_key": "aaa", "rank": 0.5}]
    qd = [{"entity_key": "aaa", "score": 0.9, "payload": {}}]
    ranked = rerank_results(pg, qd)
    assert len(ranked) == 1
    assert ranked[0]["source"] == "both"
    assert ranked[0]["combined_score"] == 1.0 + 0.9  # pg normalized to 1.0 (only result)


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
    ranked_no_graph = rerank_results(pg, qd)
    ranked_with_graph = rerank_results(pg, qd, graph_entity_keys=["aaa"])

    aaa_no_graph = next(r for r in ranked_no_graph if r["entity_key"] == "aaa")
    aaa_with_graph = next(r for r in ranked_with_graph if r["entity_key"] == "aaa")
    assert aaa_with_graph["combined_score"] > aaa_no_graph["combined_score"]
    assert aaa_with_graph["graph_boost"] == 0.1


def test_multiple_pg_normalization():
    pg = [
        {"entity_key": "a", "rank": 1.0},
        {"entity_key": "b", "rank": 0.5},
        {"entity_key": "c", "rank": 0.25},
    ]
    ranked = rerank_results(pg, [])
    scores = {r["entity_key"]: r["pg_score"] for r in ranked}
    assert scores["a"] == 1.0
    assert scores["b"] == 0.5
    assert scores["c"] == 0.25
