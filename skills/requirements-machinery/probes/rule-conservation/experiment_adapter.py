#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(f"probe_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_unit_outcome(text, case_id):
    obligations = load("obligations")
    by_cut = obligations.candidate_units(text)
    units = list(dict.fromkeys(unit for group in by_cut.values() for unit in group))
    if case_id == "step10-measurement-fields-preserved":
        fields = [
            "Definition & calculation", "Baseline", "Target", "Data source",
            "Collection frequency", "Owner", "Audience / market breakdown",
            "Attribution method", "Known limitations",
        ]
        passed = all(any(field in unit for unit in units) for field in fields)
        detail = {"all_nine_fields": passed}
    elif case_id == "step10-wrapped-quality-criterion":
        intact = any(
            "key-message inclusion" in unit
            and "positive or neutral tone" in unit
            and "original reporting vs syndication" in unit
            for unit in units
        )
        torn = any(unit.strip().startswith("or neutral tone") for unit in units)
        passed = intact and not torn
        detail = {"intact_criterion": intact, "torn_fragment": torn}
    else:
        checks = {
            "corporate": any("Corporate reputation" in u and "investor/partner confidence" in u for u in units),
            "b2b": any("B2B thought leadership" in u and "Influenced pipeline" in u for u in units),
            "employer": any("Employer branding" in u and "quality-of-hire" in u for u in units),
            "crisis": any("Crisis communications" in u and "Trust recovery" in u for u in units),
        }
        markers = (
            "investor/partner confidence", "authoritative coverage.",
            "consideration applications", "Understanding, reassurance",
        )
        torn = [u for u in units if any(u.strip().startswith(marker) for marker in markers)]
        passed = all(checks.values()) and not torn
        detail = {**checks, "torn_fragment_count": len(torn)}
    return {
        "case_id": case_id,
        "case_satisfied": passed,
        "duty_coverage": 1.0,
        "duplicate_reduction": 1.0,
        "source_unit_integrity": 1.0 if passed else 0.0,
        "item_count": len(units),
        "detail": detail,
        "items": units,
    }


def paired_outcome(case):
    cover = load("cover")
    rules = load("rules")
    rule_lineage = load("rule_lineage")
    rule_conservation = load("rule_conservation")
    target = "captured target"
    state = {
        "collapse": {
            target: {
                "entries": case["entries"],
                "merged_pairs": case["merged_pairs"],
                "owner_pairs": [],
                "owner_pair_records": [],
                "still_for_owner": [],
                "reconciled_unsettled": [],
            }
        },
        "requirements": {},
    }
    cover._read = lambda work: state
    cover._write = lambda work, value: None
    cover._last_target = lambda value: target
    rules.interview.ask_free = lambda *args, **kwargs: case["reader_quote"]

    fake_dedupe = SimpleNamespace(judge=lambda texts, reader: ([], [], []))
    fake_interview = SimpleNamespace(ask_free=lambda *args, **kwargs: "1")

    def build_checkability(replies, texts, target_name, ask):
        return {"aggregate": [{"votes": 3, "disposition": "keep"} for _ in texts]}

    fake_checkability = SimpleNamespace(build=build_checkability)
    modules = {
        "rules": rules,
        "dedupe": fake_dedupe,
        "interview": fake_interview,
        "checkability": fake_checkability,
        "rule_lineage": rule_lineage,
        "rule_conservation": rule_conservation,
    }
    cover._load = lambda name: modules[name]
    exit_code = cover.requirements("/captured-case", "reader")
    items = state["requirements"][target]["items"]
    texts = [item["text"] for item in items]
    required = case["required_phrases"]
    preserved = {phrase: any(phrase in text for text in texts) for phrase in required}
    duty_coverage = sum(preserved.values()) / len(preserved)
    within_bound = len(texts) <= case["maximum_items"]
    duplicate_reduction = (
        1.0 if case["case_id"] != "step10-genuine-duplicate"
        else float(len(texts) == 1)
    )
    return {
        "case_id": case["case_id"],
        "case_satisfied": exit_code == 0 and duty_coverage == 1.0 and within_bound,
        "exit_code": exit_code,
        "duty_coverage": duty_coverage,
        "duplicate_reduction": duplicate_reduction,
        "source_unit_integrity": 1.0,
        "item_count": len(texts),
        "maximum_items": case["maximum_items"],
        "preserved": preserved,
        "items": texts,
        "source_conservation": state["requirements"][target].get("source_conservation"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    payload = Path(args.input).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    case_ids = {
        "be1ed0f8aa929f5bb751fa05bafe1bc20ec5cecdb4b7a6c6714bc5c44d15bedd": "step10-measurement-fields-preserved",
        "79ed9c39b496b0337d2f3f48eea1a083d4d84f117f8b91922401fdee1c957d1a": "step10-wrapped-quality-criterion",
        "429b6f9c8f08f05fc6397f19bf509df6628118f26acfb17e9700eb5de30472a2": "step10-multicolumn-kpi-rows",
    }
    try:
        case = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        case = None
    if isinstance(case, dict) and case.get("kind") == "paired-duty-conservation":
        outcome = paired_outcome(case)
    else:
        outcome = source_unit_outcome(payload.decode(), case_ids[digest])
    metrics = {
        "duty-coverage": outcome["duty_coverage"],
        "duplicate-reduction": outcome["duplicate_reduction"],
        "source-unit-integrity": outcome["source_unit_integrity"],
        "item-count": float(outcome["item_count"]),
    }
    result = {
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": outcome,
        "metrics": metrics,
        "error": None,
    }
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
