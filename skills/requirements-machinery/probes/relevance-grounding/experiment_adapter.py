#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_relevance():
    path = ROOT / "scripts" / "relevance.py"
    spec = importlib.util.spec_from_file_location("probe_relevance", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prompt_version(question):
    if question.startswith("You said this page constrains"):
        return "canonical"
    if question.startswith("The page was already classified YES"):
        return "changed"
    raise ValueError("unrecognized relevance quote prompt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    case = json.loads(Path(args.input).read_text())
    relevance = load_relevance()
    version = prompt_version(relevance.QUOTE_QUESTION)
    records = [r for r in case["records"] if r["prompt_version"] == version]
    counts = {name: sum(r["outcome"] == name for r in records) for name in (
        "source-exact", "no-such-words", "ungrounded", "unparseable"
    )}
    total = len(records)
    source_exact_rate = counts["source-exact"] / total
    missing_evidence_rate = (counts["no-such-words"] + counts["unparseable"]) / total
    ungrounded_rate = counts["ungrounded"] / total
    specificity = float(
        "already classified YES" in relevance.QUOTE_QUESTION
        and "exact excerpt" in relevance.QUOTE_QUESTION
        and "does not need to repeat" in relevance.QUOTE_QUESTION
    )
    if case.get("input_sha256"):
        satisfied = source_exact_rate == 1.0 and missing_evidence_rate == 0.0 and ungrounded_rate == 0.0
    else:
        satisfied = source_exact_rate >= 0.9 and missing_evidence_rate <= 0.05 and ungrounded_rate <= 0.05
    outcome = {
        "case_satisfied": satisfied,
        "prompt_version": version,
        "record_count": total,
        "counts": counts,
        "source_exact_rate": source_exact_rate,
        "missing_evidence_rate": missing_evidence_rate,
        "ungrounded_response_rate": ungrounded_rate,
        "prompt_contract_specificity": specificity,
        "downstream_contract": "ask_quote accepts only a source substring; other text remains ungrounded",
    }
    result = {
        "schema_version": 1,
        "variant_id": os.environ["EXPERIMENT_VARIANT_ID"],
        "status": "completed",
        "outcome": outcome,
        "metrics": {
            "source-exact-rate": source_exact_rate,
            "missing-evidence-rate": missing_evidence_rate,
            "ungrounded-response-rate": ungrounded_rate,
            "prompt-contract-specificity": specificity,
        },
        "error": None,
    }
    Path(args.result).write_text(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
