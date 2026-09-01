#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def contains_all(candidate, terms):
    folded = candidate.casefold()
    return all(term.casefold() in folded for term in terms)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    payload = Path(args.input).read_bytes()
    text = payload.decode()
    digest = hashlib.sha256(payload).hexdigest()
    cases = {
        "79ed9c39b496b0337d2f3f48eea1a083d4d84f117f8b91922401fdee1c957d1a": "step10-wrapped-quality-criterion",
        "429b6f9c8f08f05fc6397f19bf509df6628118f26acfb17e9700eb5de30472a2": "step10-multicolumn-kpi-rows",
        "be1ed0f8aa929f5bb751fa05bafe1bc20ec5cecdb4b7a6c6714bc5c44d15bedd": "step10-measurement-fields-preserved",
    }
    case_id = cases[digest]
    obligations = load("obligations")
    quotecheck = load("quotecheck")
    by_cut = obligations.candidate_units(text)
    offered = list(dict.fromkeys(unit for units in by_cut.values() for unit in units))
    grounded = [unit for unit in offered if quotecheck.check(unit, text)]
    torn = {
        "Score each item against: priority outlet/influencer · priority-audience relevance · key-message inclusion · positive",
        "or neutral tone · brand/spokesperson prominence · desired call to action · original reporting vs syndication.",
        "B2B thought leadership Output: decision-maker reach & Senior engagement, content Influenced pipeline and",
        "Corporate reputation Trust, perceived leadership, association with Stakeholder engagement, advocacy, Reputation score, licence to",
        "Crisis communications Output: response speed, message Complaint behaviour, stakeholder Trust recovery, reduced",
        "Employer branding Employer awareness, understanding of EVP, Career-page visits, qualified Time-to-hire, cost-per-hire,",
        "Understanding, reassurance, misinformation conversation",
        "authoritative coverage. Recognition of consumption, qualified leads, sales revenue",
        "consideration applications, offer acceptance retention / quality-of-hire",
        "consistency, stakeholder coverage. support, recovery of positive/neutral customer loss, risk avoided",
        "desired attributes meeting requests, partner interest operate, risk reduction,",
        "expertise & issue understanding conversations",
        "investor/partner confidence",
    }
    torn_found = sorted(set(grounded) & torn)
    required_units = []
    preserved_terms = []
    required_terms = []
    if case_id == "step10-wrapped-quality-criterion":
        criterion_terms = [
            "Score each item against:", "priority outlet/influencer", "positive or neutral tone",
            "brand/spokesperson prominence", "original reporting vs syndication",
        ]
        share_terms = [
            "Share of voice — use only when:", "competitor & topic set", "starting position in each market",
        ]
        required_units = [
            any(contains_all(unit, criterion_terms) and len(unit) <= 600 for unit in grounded),
            any(contains_all(unit, share_terms) for unit in grounded),
        ]
        required_terms = criterion_terms + share_terms
    elif case_id == "step10-multicolumn-kpi-rows":
        rows = [
            ["Corporate reputation", "Trust, perceived leadership", "Stakeholder engagement, advocacy", "investor/partner confidence"],
            ["B2B thought leadership", "decision-maker reach", "Senior engagement, content", "Influenced pipeline", "revenue"],
            ["Employer branding", "understanding of EVP", "Career-page visits", "retention / quality-of-hire"],
            ["Crisis communications", "response speed", "Complaint behaviour", "customer loss, risk avoided"],
        ]
        required_units = [any(contains_all(unit, row) for unit in grounded) for row in rows]
        required_terms = [term for row in rows for term in row]
    else:
        required_terms = [
            "Measurement design — record for every KPI", "Definition & calculation", "Baseline", "Target",
            "Data source", "Collection frequency", "Owner", "Audience / market breakdown",
            "Attribution method", "Known limitations",
        ]
        all_grounded = " ".join(grounded)
        required_units = [contains_all(all_grounded, required_terms)]
    joined = " ".join(grounded)
    preserved_terms = [term for term in required_terms if term.casefold() in joined.casefold()]
    exact_grounding = len(grounded) == len(offered)
    satisfied = all(required_units) and not torn_found and len(preserved_terms) == len(required_terms)
    outcome = {
        "approach_id": getattr(obligations._reflow, "STRATEGY", "physical-cuts-control"),
        "case_id": case_id,
        "case_sha256": digest,
        "case_satisfied": satisfied,
        "candidate_count": len(grounded),
        "complete_unit_count": sum(required_units),
        "required_unit_count": len(required_units),
        "exact_grounding": exact_grounding,
        "grounded_candidate_count": len(grounded),
        "offered_candidate_count": len(offered),
        "preserved_term_count": len(preserved_terms),
        "required_term_count": len(required_terms),
        "torn_candidate_count": len(torn_found),
        "torn_candidates": torn_found,
        "units": grounded,
    }

    metrics = {
        "structure-completeness": outcome["complete_unit_count"] / outcome["required_unit_count"],
        "torn-fragment-absence": 1.0 if outcome["torn_candidate_count"] == 0 else 0.0,
        "source-grounding": 1.0 if outcome["exact_grounding"] else 0.0,
        "term-preservation": outcome["preserved_term_count"] / outcome["required_term_count"],
        "candidate-count": float(outcome["candidate_count"]),
    }
    result = {
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": outcome,
        "metrics": metrics,
        "error": None,
    }
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
