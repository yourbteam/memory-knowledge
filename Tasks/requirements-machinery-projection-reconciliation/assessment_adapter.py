#!/usr/bin/env python3
"""Assess the composed reconciliation against each declared real case."""

import json
import sys
from pathlib import Path


request = json.loads(Path(sys.argv[1]).read_text())
outcome = request["execution_result"]["outcome"]
case_id = request["case_id"]
if case_id == "step7-chain-remains-complete":
    chain = outcome["chain"]
    satisfied = (
        outcome.get("controller_available") is True
        and outcome.get("exit_codes") == [0, 0]
        and outcome.get("runtime_identity") == "snapshot"
        and outcome.get("policy_drift_survived") is True
        and chain.get("valid") is True
        and chain.get("source_count") == 35
        and chain.get("represented_count") == 35
        and chain.get("six_type_ids") == [11, 27]
    )
    reason = "the reconciled controller resumes through a pinned runtime and all 35 rule identities survive"
elif case_id == "codex-installed-behavior-is-not-erased":
    satisfied = all([
        outcome.get("client") == "codex",
        outcome.get("chain_modules_present") is True,
        outcome.get("recommended_reader_correct") is True,
        outcome.get("full_outer_boundary") is True,
        outcome.get("client_runtime_preserved") is True,
    ])
    reason = "the generated Codex projection retains the exact read-only nested command and required outer launch"
else:
    satisfied = all([
        outcome.get("client") == "claude",
        outcome.get("chain_modules_present") is True,
        outcome.get("recommended_reader_correct") is True,
        outcome.get("full_outer_boundary") is True,
        outcome.get("client_runtime_preserved") is True,
    ])
    reason = "the generated Claude projection receives shared conservation code and remains Claude-owned"
Path(sys.argv[2]).write_text(json.dumps({
    "case_id": case_id,
    "verdict": "satisfied" if satisfied else "not-satisfied",
    "reason": reason,
    "evidence_pointers": ["execution-result"],
}, indent=2, sort_keys=True) + "\n")
