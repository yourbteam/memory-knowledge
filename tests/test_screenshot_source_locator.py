from pathlib import Path

from scripts import screenshot_source_locator as locator


def test_empty_repository_stops_before_cross_directory_search(tmp_path: Path):
    result = locator.search(tmp_path, ["Billing Information", "Payment Information"])

    assert result["status"] == "empty-repository"
    assert "Confirm the actual checkout" in result["next_action"]


def test_candidates_are_ranked_by_distinct_stable_terms(tmp_path: Path):
    view = tmp_path / "Views" / "ClientProfile.cshtml"
    script = tmp_path / "scripts" / "client-profile.js"
    view.parent.mkdir()
    script.parent.mkdir()
    view.write_text("Billing Information\nPayment Information\nCustomer Type\n", encoding="utf-8")
    script.write_text("// Payment Information behavior\n", encoding="utf-8")

    result = locator.search(
        tmp_path,
        ["Billing Information", "Payment Information", "Customer Type"],
    )

    assert result["status"] == "candidates-found"
    assert result["candidate_files"][0]["file"] == "Views/ClientProfile.cshtml"
    assert result["candidate_files"][0]["distinct_term_count"] == 3
    assert result["candidate_files"][1]["file"] == "scripts/client-profile.js"


def test_generated_and_dependency_trees_are_excluded(tmp_path: Path):
    source = tmp_path / "src" / "page.tsx"
    dependency = tmp_path / "node_modules" / "package" / "page.js"
    generated = tmp_path / "dist" / "page.js"
    source.parent.mkdir()
    dependency.parent.mkdir(parents=True)
    generated.parent.mkdir()
    source.write_text("Billing Information", encoding="utf-8")
    dependency.write_text("Billing Information", encoding="utf-8")
    generated.write_text("Billing Information", encoding="utf-8")

    result = locator.search(tmp_path, ["Billing Information"])

    assert [candidate["file"] for candidate in result["candidate_files"]] == ["src/page.tsx"]


def test_no_match_returns_the_fallback_funnel(tmp_path: Path):
    (tmp_path / "README.md").write_text("unrelated", encoding="utf-8")

    result = locator.search(tmp_path, ["Billing Information"])

    assert result["status"] == "no-matches"
    assert "localization keys" in result["next_action"]
