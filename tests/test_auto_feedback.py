"""Tests for auto-generated route feedback heuristics."""
import pytest

from memory_knowledge.workflows.retrieval import compute_auto_feedback


def _make_results(scores, source="postgres"):
    """Helper to build ranked_results dicts."""
    return [{"combined_score": s, "source": source} for s in scores]


# ── Usefulness: per-class ideal range ──


def test_zero_results_conceptual():
    fb = compute_auto_feedback(
        [], 0, False, False, ["qdrant"], "conceptual_lookup", 50
    )
    assert fb["usefulness_score"] == 0.05
    assert fb["precision_score"] == 0.05
    assert fb["expansion_needed"] is True
    assert "[auto]" in fb["notes"]


def test_exact_lookup_in_ideal_range():
    fb = compute_auto_feedback(
        _make_results([1.0, 0.8]), 2, False, False, ["postgres"], "exact_lookup", 45
    )
    assert fb["usefulness_score"] == 0.70
    assert fb["expansion_needed"] is False


def test_exact_lookup_above_ideal_range():
    results = _make_results([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2])
    fb = compute_auto_feedback(
        results, 8, False, False, ["postgres"], "exact_lookup", 60
    )
    # 8 > 5 (high). 0.55 - 0.10 * min((8-5)/5, 1.0) = 0.55 - 0.06 = 0.49
    assert fb["usefulness_score"] == 0.49


def test_conceptual_lookup_in_range_with_bonus():
    results = _make_results([1.8, 1.5, 1.2, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2, 0.1,
                             0.1, 0.1, 0.1, 0.1, 0.1])
    fb = compute_auto_feedback(
        results, 15, False, True, ["postgres", "qdrant"], "conceptual_lookup", 200
    )
    # In range [5,20] → 0.70. Top-3 avg = (1.8+1.5+1.2)/3 = 1.5 >= 1.0 → +0.10 = 0.80
    assert fb["usefulness_score"] == 0.80


def test_conceptual_lookup_below_range():
    results = _make_results([0.6, 0.3])
    fb = compute_auto_feedback(
        results, 2, False, False, ["qdrant"], "conceptual_lookup", 80
    )
    # 2 < 5. 0.25 + 0.35 * (2/5) = 0.25 + 0.14 = 0.39
    assert fb["usefulness_score"] == 0.39
    assert fb["expansion_needed"] is True


# ── Precision: store-count-aware ──


def test_precision_single_store():
    results = _make_results([1.0, 0.8])
    fb = compute_auto_feedback(
        results, 2, False, False, ["postgres"], "exact_lookup", 30
    )
    # avg_top5 = 0.9, stores=1, 0.9/1.0 * 0.85 = 0.765
    # spread = 0.2 < 0.5, no bonus
    assert abs(fb["precision_score"] - 0.77) < 0.02


def test_precision_multi_store_with_spread_bonus():
    results = _make_results([1.8, 1.5, 1.2, 0.9, 0.7], source="both")
    fb = compute_auto_feedback(
        results, 5, False, False, ["postgres", "qdrant"], "conceptual_lookup", 150
    )
    # avg_top5 = 1.22, stores=2, base = 1.22/2.0 * 0.85 = 0.5185
    # spread = 1.8 - 0.7 = 1.1 > 0.5 → +0.10 = ~0.62
    assert abs(fb["precision_score"] - 0.62) < 0.02


# ── Caps ──


def test_scores_capped():
    results = _make_results([2.1] * 15, source="both")
    fb = compute_auto_feedback(
        results, 15, True, True, ["postgres", "qdrant", "neo4j"], "impact_analysis", 500
    )
    assert fb["usefulness_score"] <= 0.85
    assert fb["precision_score"] <= 0.85


# ── Notes ──


def test_notes_structured():
    results = _make_results([0.8])
    fb = compute_auto_feedback(
        results, 1, False, False, ["qdrant"], "conceptual_lookup", 120
    )
    assert fb["notes"].startswith("[auto]")
    assert "class=conceptual_lookup" in fb["notes"]
    assert "stores=qdrant" in fb["notes"]
    assert "duration=120ms" in fb["notes"]


# ── Fallback for unknown prompt_class ──


def test_unknown_prompt_class_falls_back_to_mixed():
    results = _make_results([0.9, 0.7, 0.5, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1])
    fb = compute_auto_feedback(
        results, 10, False, False, ["postgres"], "some_future_class", 100
    )
    # Should use mixed profile ideal_range (5, 20) — 10 is in range → 0.70
    assert fb["usefulness_score"] == 0.70
    assert fb["expansion_needed"] is False
