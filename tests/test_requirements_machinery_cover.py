"""Focused real-path contracts for the repository-owned Requirements Machinery."""
from __future__ import annotations

import copy
import importlib.util
import json
import hashlib
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
MACHINERY = ROOT / "skills" / "requirements-machinery"
COVER = MACHINERY / "scripts" / "cover.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def bind_run_identity(run: Path, state: dict) -> dict:
    """Bind a synthetic state fixture to real immutable source and piece artifacts."""
    run.mkdir(parents=True, exist_ok=True)
    source = run / "source.pdf"
    source.write_bytes(b"fixture source")
    state["source"] = str(source.resolve())
    state["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    pieces = run / "pieces"
    pieces.mkdir(parents=True, exist_ok=True)
    for piece in state.get("pieces", []):
        path = pieces / f"{piece['id']}.txt"
        if not path.exists():
            path.write_text(f"fixture piece {piece['id']}", encoding="utf-8")
        payload = path.read_bytes()
        piece["sha256"] = hashlib.sha256(payload).hexdigest()
        piece["chars"] = len(payload.decode("utf-8"))
    return state


def test_published_command_surface_matches_real_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(MACHINERY / "scripts" / "contract_surface.py"),
            "--skill", str(MACHINERY / "SKILL.md"),
            "--cover", str(COVER),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    result = json.loads(completed.stdout)
    assert result["parity"] is True
    assert result["documented"] == result["executable"] == 15
    assert set(result["categories"].values()) == {
        "coverage", "extraction", "owner decision", "document assembly",
    }


def test_documented_answer_example_executes_its_state_transition() -> None:
    text = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    index = next(
        position for position, line in enumerate(lines)
        if line.startswith("python3 scripts/cover.py answer ")
    )
    command = [lines[index]]
    while command[-1].rstrip().endswith("\\"):
        command[-1] = command[-1].rstrip()[:-1]
        index += 1
        command.append(lines[index].strip())
    tokens = shlex.split(" ".join(command))
    quote = "A substantive source statement for the target document."
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        (run / "pieces").mkdir(parents=True)
        (run / "pieces" / "p-0007.txt").write_text(quote + "\n", encoding="utf-8")
        (run / "coverage.json").write_text(json.dumps(bind_run_identity(run, {
            "source": "fixture.pdf", "source_sha256": "a" * 64, "strategy": "fixture",
            "opened_at": 0, "pieces": [{
                "id": "p-0007", "chars": len(quote) + 1,
                "sha256": hashlib.sha256((quote + "\n").encode()).hexdigest(),
            }], "answers": {},
        })), encoding="utf-8")
        replacements = {
            "<dir>": str(run), "<words from the piece>": quote,
            "...": "Captured source meaning.",
        }
        argv = [replacements.get(token, token) for token in tokens]
        argv[0], argv[1] = sys.executable, str(COVER)

        subprocess.run(argv, check=True, capture_output=True, text=True)

        state = json.loads((run / "coverage.json").read_text(encoding="utf-8"))
        assert state["answers"]["p-0007"]["quote"] == quote


def test_manual_and_reader_grounding_share_one_substantive_contract() -> None:
    quotecheck = load("requirements_quotecheck", MACHINERY / "scripts" / "quotecheck.py")
    interview = load("requirements_interview", MACHINERY / "scripts" / "interview.py")
    cover = load("requirements_cover_grounding", COVER)
    piece = "This substantive source\nstatement carries enough grounding words."
    normalized = "This substantive source statement carries enough grounding words."

    assert quotecheck.grounding("", piece) is None
    assert quotecheck.grounding("   \n", piece) is None
    assert quotecheck.grounding("This substantive", piece) is None
    assert quotecheck.grounding(normalized, piece) == normalized
    assert quotecheck.grounding("Short rule.", "Short rule.") == "Short rule."
    interview._spawn = lambda *_args, **_kwargs: normalized
    assert interview.ask_quote("fixture-reader", "quote", piece, quotecheck)[0] == normalized

    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        (run / "pieces").mkdir(parents=True)
        (run / "pieces" / "p-0001.txt").write_text(piece, encoding="utf-8")
        (run / "coverage.json").write_text(json.dumps(bind_run_identity(run, {
            "source": "fixture.pdf", "source_sha256": "a" * 64, "strategy": "fixture",
            "opened_at": 0, "pieces": [{
                "id": "p-0001", "chars": len(piece),
                "sha256": hashlib.sha256(piece.encode()).hexdigest(),
            }], "answers": {},
        })), encoding="utf-8")
        assert cover.answer(run, "p-0001", "reader-1", "meaning", normalized) == 0
        state = json.loads((run / "coverage.json").read_text(encoding="utf-8"))
        assert state["answers"]["p-0001"]["quote"] == normalized


def test_public_disclosure_and_private_state_boundary_are_exact() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        (run / "pieces").mkdir(parents=True)
        state = {
            "source": "fixture.pdf", "source_sha256": "a" * 64, "strategy": "fixture",
            "opened_at": 0,
            "pieces": [
                {"id": "p-0001", "chars": 1, "sha256": "b" * 64},
                {"id": "p-0002", "chars": 1, "sha256": "c" * 64},
            ],
            "answers": {"p-0001": {
                "what": "SECRET-ONE", "quote": "SECRET-QUOTE-ONE",
                "by": "reader-1", "at": 1,
            }},
        }
        state_path = run / "coverage.json"
        bind_run_identity(run, state)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        status = subprocess.run(
            [sys.executable, str(COVER), "status", "--work", str(run)],
            check=True, capture_output=True, text=True,
        )
        incomplete = subprocess.run(
            [sys.executable, str(COVER), "report", "--work", str(run)],
            capture_output=True, text=True,
        )
        assert "SECRET-ONE" not in status.stdout + incomplete.stdout + incomplete.stderr
        assert incomplete.returncode == 3
        assert "SECRET-ONE" in state_path.read_text(encoding="utf-8")

        state["answers"]["p-0002"] = {
            "what": "SECRET-TWO", "quote": "SECRET-QUOTE-TWO",
            "by": "reader-2", "at": 2,
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        complete = subprocess.run(
            [sys.executable, str(COVER), "report", "--work", str(run)],
            check=True, capture_output=True, text=True,
        )
        assert "SECRET-ONE" in complete.stdout and "SECRET-TWO" in complete.stdout
        contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
        assert "not a filesystem-confidentiality guarantee" in contract


def test_reader_execution_outcomes_fail_closed_before_semantic_parsing(monkeypatch) -> None:
    interview = load("requirements_interview_execution", MACHINERY / "scripts" / "interview.py")
    with tempfile.TemporaryDirectory() as directory:
        feed = Path(directory) / "feed.jsonl"
        monkeypatch.setenv("REQ_MACHINERY_FEED", str(feed))
        monkeypatch.setenv("REQ_MACHINERY_READER_TIMEOUT_SECONDS", "0.05")
        fixture = Path(directory) / "fake_reader.py"
        fixture.write_text('import sys\nimport time\n\nmode = sys.argv[1]\nif mode == "success":\n    print("NO")\nelif mode == "nonzero-stdout":\n    print("YES")\n    raise SystemExit(7)\nelif mode == "timeout":\n    time.sleep(1)\n    print("YES")\nelif mode == "malformed":\n    print("MAYBE")\nelse:\n    raise SystemExit(9)\n', encoding="utf-8")

        def command(mode: str) -> str:
            return " ".join(shlex.quote(part) for part in (sys.executable, str(fixture), mode))

        assert interview._spawn(command("success"), "question", "test") == "NO"
        with pytest.raises(SystemExit) as nonzero:
            interview._spawn(command("nonzero-stdout"), "question", "test")
        assert nonzero.value.code == 4
        with pytest.raises(SystemExit) as timeout:
            interview._spawn(command("timeout"), "question", "test")
        assert timeout.value.code == 4
        answer, transcript = interview.ask_choice(
            command("malformed"), "question", ["YES", "NO"])
        assert answer is None and len(transcript) == 3

        events = [json.loads(line) for line in feed.read_text(encoding="utf-8").splitlines()]
        outcomes = {event.get("outcome") for event in events}
        assert {"zero-exit", "nonzero-exit", "timeout", "malformed-reply"} <= outcomes
        assert not any(event.get("outcome") == "valid-reply" for event in events)
        assert "reader process" not in "".join(json.dumps(event) for event in events)

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "180 seconds by default" in contract
    assert "only a zero-exit reply reaches semantic validation" in contract

def test_reader_policy_is_validated_at_every_cli_command_boundary() -> None:
    commands = {
        "relevance": ["--target", "target requirements"],
        "obligations": [], "collapse": [], "requirements": [], "distill": [],
        "ask-owner": [],
        "answer-owner": ["--id", "decision-1", "--choice", "keep"],
        "document": ["--out", "OUTPUT"],
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        root = Path(directory)
        projected = root / "requirements-machinery"
        shutil.copytree(MACHINERY, projected)
        (projected / "client-model-policy.json").write_text(json.dumps({
            "schema_version": 1, "client": "test-client",
            "required_runtime": "/bin/echo",
            "recommended_reader_command": "/bin/echo NO", "fail_closed": True,
        }), encoding="utf-8")
        cover = projected / "scripts" / "cover.py"
        absent = root / "absent"
        for command, raw_extra in commands.items():
            extra = [str(root / "out.md") if value == "OUTPUT" else value for value in raw_extra]
            completed = subprocess.run([
                sys.executable, str(cover), command, "--work", str(absent), *extra,
                "--reader-command", "/bin/echo BAD",
            ], capture_output=True, text=True)
            assert completed.returncode != 0
            assert "projection refuses reader command" in completed.stderr

        run = root / "reuse"
        (run / "pieces").mkdir(parents=True)
        piece = "Reader policy fixture."
        (run / "pieces" / "p-0001.txt").write_text(piece, encoding="utf-8")
        (run / "coverage.json").write_text(json.dumps(bind_run_identity(run, {
            "source": "fixture.pdf", "source_sha256": "a" * 64,
            "strategy": "fixture", "opened_at": 0,
            "pieces": [{"id": "p-0001", "chars": len(piece),
                        "sha256": hashlib.sha256(piece.encode()).hexdigest()}],
            "answers": {}, "relevance": {"last": "target requirements", "targets": {
                "target requirements": {"pieces": {"p-0001": {
                    "verdict": "does-not-bear", "seats": [], "at": 1,
                }}}
            }},
        })), encoding="utf-8")
        feed = run / "feed.jsonl"
        env = os.environ.copy()
        env["REQ_MACHINERY_FEED"] = str(feed)
        completed = subprocess.run([
            sys.executable, str(cover), "relevance", "--work", str(run),
            "--target", "target requirements", "--reader-command", "/bin/echo NO",
        ], check=True, capture_output=True, text=True, env=env)
        assert not feed.exists()

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "Commands validate a supplied `--reader-command` at CLI entry" in contract


def test_checkability_record_replays_and_detects_evidence_tampering() -> None:
    checkability = load("requirements_checkability", MACHINERY / "scripts" / "checkability.py")
    items = ["The document must name one accountable owner."]
    target = "target requirements"
    prompt = "Frozen prompt for target requirements and item 1."
    record = checkability.build(["1\nnoise", "1", "2"], items, target, prompt)

    assert checkability.validate(record, items, target, prompt) == record
    assert [seat["parsed_selections"] for seat in record["seats"]] == [[1], [1], []]
    assert record["aggregate"] == [{"item": 1, "votes": 2, "disposition": "owner"}]
    assert all("raw_reply" in seat and "validation" in seat for seat in record["seats"])

    tampered = json.loads(json.dumps(record))
    tampered["seats"][0]["raw_reply"] = "CHANGED"
    with pytest.raises(ValueError, match="integrity mismatch"):
        checkability.validate(tampered, items, target, prompt)

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "all three raw replies" in contract
    assert "any evidence or derived-field drift fails closed" in contract


def test_no_answer_piece_is_a_first_class_owner_decision() -> None:
    cover = load("requirements_cover_no_answer", COVER)
    target = "target requirements"
    state = {
        "_work": str(ROOT / "Tasks"),
        "relevance": {"targets": {target: {"pieces": {
            "p-0007": {"verdict": "no-answer", "seats": []},
        }}}},
        "distilled": {target: {"items": [], "owner_pairs": [],
                               "still_for_owner": ["p-0007"]}},
        "owner_rulings": {target: {}},
    }
    queue = cover._owner_queue(state, target)

    assert len(queue) == 1
    assert queue[0]["id"] == "piece-p-0007"
    assert queue[0]["relevance_verdict"] == "no-answer"
    assert queue[0]["choices"] == ["admit", "dismiss"]
    assert "without a valid answer" in queue[0]["why"]

    state["owner_rulings"][target]["piece-p-0007"] = {
        "item": queue[0], "choice": "dismiss", "because": "owner ruling",
    }
    assert cover._owner_queue(state, target) == []

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "A `no-answer` verdict never disappears" in contract


def test_completed_empty_obligations_are_distinct_from_absence() -> None:
    cover = load("requirements_cover_empty_obligations", COVER)
    target = "target requirements"
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        (run / "pieces").mkdir(parents=True)
        piece = "A source page with no obligation for this target."
        (run / "pieces" / "p-0001.txt").write_text(piece, encoding="utf-8")
        state = {
            "source": "fixture.pdf", "source_sha256": "a" * 64,
            "strategy": "fixture", "opened_at": 0,
            "pieces": [{"id": "p-0001", "chars": len(piece),
                        "sha256": hashlib.sha256(piece.encode()).hexdigest()}],
            "answers": {}, "relevance": {"last": target, "targets": {target: {"pieces": {
                "p-0001": {"verdict": "does-not-bear", "seats": [], "at": 1},
            }}}},
        }
        state_path = run / "coverage.json"
        bind_run_identity(run, state)
        state_path.write_text(json.dumps(state), encoding="utf-8")

        assert cover.collapse(run, "unused-reader") == 3
        assert cover.obligations(run, "unused-reader") == 0
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert persisted["obligations"][target] == {}
        assert persisted["obligation_completion"][target]["complete"] is True
        assert persisted["obligation_completion"][target]["piece_ids"] == []
        assert cover.collapse(run, "unused-reader") == 0
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert persisted["collapse"][target]["entries"] == []

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "records completion separately from its collection" in contract


def test_first_dedupe_owner_pair_has_stable_complete_queue_identity() -> None:
    cover = load("requirements_cover_source_pair", COVER)
    target = "target requirements"
    pair = {
        "id": "source-pair-deadbeef1234",
        "a": {"piece": "p-0001", "text": "First complete source-supported statement."},
        "b": {"piece": "p-0002", "text": "Second complete source-supported statement."},
        "evidence": {"votes": ["YES", "NO", "YES", "NO"], "verdict": "owner"},
    }
    state = {
        "distilled": {target: {"items": [], "owner_pairs": [],
                               "source_owner_pairs": [pair], "still_for_owner": []}},
        "owner_rulings": {target: {}},
    }
    first = cover._owner_queue(state, target)
    second = cover._owner_queue(json.loads(json.dumps(state)), target)

    assert first == second and len(first) == 1
    assert first[0]["id"] == pair["id"]
    assert first[0]["a"] == pair["a"]["text"] and first[0]["b"] == pair["b"]["text"]
    assert first[0]["evidence"] == pair["evidence"]
    assert first[0]["choices"] == ["merge", "keep-separate"]

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "Every first-deduplication owner pair" in contract


def test_failed_shared_rule_preserves_both_sources_and_attempts() -> None:
    cover = load("requirements_cover_shared_rule", COVER)
    target = "target requirements"
    record = {
        "id": "shared-rule-deadbeef1234",
        "a": {"piece": "p-0001", "text": "First source duty remains complete."},
        "b": {"piece": "p-0002", "text": "Second source duty remains complete."},
        "extraction": {"rule": None, "attempts": ["bad-1", "bad-2", "bad-3", "bad-4"]},
    }
    state = {
        "distilled": {target: {"items": [], "owner_pairs": [], "source_owner_pairs": [],
                               "shared_rule_owner_records": [record], "still_for_owner": []}},
        "owner_rulings": {target: {}},
    }
    queue = cover._owner_queue(state, target)

    assert len(queue) == 1 and queue[0]["id"] == record["id"]
    assert queue[0]["a"] == record["a"]["text"] and queue[0]["b"] == record["b"]["text"]
    assert queue[0]["extraction"] == record["extraction"]
    assert queue[0]["choices"] == ["keep-both", "select-a", "select-b"]

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "When a merged pair yields no verbatim shared rule" in contract


def test_checkability_identity_changes_with_the_active_target() -> None:
    checkability = load("requirements_checkability_target", MACHINERY / "scripts" / "checkability.py")
    items = ["The artifact must name an accountable owner."]
    alpha_target, beta_target = "Alpha launch brief", "Beta evidence register"
    alpha_prompt = f"The document they are for is: {alpha_target}\n\n1. {items[0]}"
    beta_prompt = f"The document they are for is: {beta_target}\n\n1. {items[0]}"
    alpha = checkability.build(["1", "1", "1"], items, alpha_target, alpha_prompt)
    beta = checkability.build(["1", "1", "1"], items, beta_target, beta_prompt)

    assert alpha["target"] == alpha_target and beta["target"] == beta_target
    assert alpha["target_sha256"] != beta["target_sha256"]
    assert alpha["prompt_sha256"] != beta["prompt_sha256"]
    assert alpha["record_sha256"] != beta["record_sha256"]
    assert "Step 3 Measurement Brief" not in alpha_prompt + beta_prompt

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "Checkability is always target-bound" in contract


def test_zero_ruling_absence_and_explicit_empty_assemble_identically() -> None:
    cover = load("requirements_cover_zero_rulings", COVER)
    target = "target requirements"
    statement = "The final artifact must name one accountable owner."
    base = {
        "source": "fixture.pdf", "source_sha256": "a" * 64, "strategy": "fixture",
        "opened_at": 0, "pieces": [], "answers": {}, "relevance": {"last": target},
        "distilled": {target: {"items": [{
            "pages": ["p-0001"], "statement": statement, "how": "verbatim",
            "anchors": [statement], "checkable": True, "doubt": None,
        }], "owner_pairs": [], "source_owner_pairs": [],
            "shared_rule_owner_records": [], "still_for_owner": []}},
        "requirements": {target: {"rules_stage": {"rules": []},
                                  "rule_judgement": {"texts": [], "merged": []}}},
        "collapse": {target: {"entries": []}},
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        root = Path(directory)
        texts = []
        for name, explicit in (("absent", False), ("explicit", True)):
            run = root / name
            run.mkdir()
            state = json.loads(json.dumps(base))
            if explicit:
                state["owner_rulings"] = {target: {}}
            bind_run_identity(run, state)
            (run / "coverage.json").write_text(json.dumps(state), encoding="utf-8")
            out = root / f"{name}.md"
            assert cover.document(run, out) == 0
            texts.append(out.read_text(encoding="utf-8"))
        assert texts[0] == texts[1]

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "byte-identical documents" in contract


def test_conflicting_source_selection_reopens_and_corrects_through_cli() -> None:
    target = "fixture requirements"
    kept = ("Every quality gate tests this line of sight; anything orphaned goes to the "
            "appendix, never the strategy.")
    dropped = "Every step maps to its exact quality gate and deliverable."
    pair_id = "pair-" + hashlib.sha256((kept + "||" + dropped).encode()).hexdigest()[:8]
    check_item = {
        "id": "check-1", "kind": "checkability", "question": "Does this belong?",
        "statement": dropped, "pages": ["p-0002"], "anchors": [dropped],
        "choices": ["keep", "drop", "split"],
    }
    pair_item = {
        "id": pair_id, "kind": "overlap", "question": "Do these state the same rule?",
        "a": kept, "b": dropped, "statement": f"A: {kept}\nB: {dropped}",
        "pages": [], "choices": ["merge", "keep-separate"],
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        state = bind_run_identity(run, {
            "strategy": "fixture", "opened_at": 0,
            "pieces": [
                {"id": "p-0001", "chars": 0, "sha256": ""},
                {"id": "p-0002", "chars": 0, "sha256": ""},
            ],
            "answers": {}, "relevance": {"target": target},
            "distilled": {target: {
                "items": [{
                    "pages": ["p-0002"], "statement": dropped, "how": "pen",
                    "anchors": [dropped], "checkable": False,
                }],
                "owner_pairs": [[kept, dropped]], "source_owner_pairs": [],
                "shared_rule_owner_records": [], "still_for_owner": [],
            }},
            "owner_rulings": {target: {
                "check-1": {"item": check_item, "choice": "drop", "because": "not in scope"},
                pair_id: {"item": pair_item, "choice": "keep-separate", "because": "distinct"},
            }},
            "requirements": {target: {
                "rules_stage": {"rules": [
                    {"text": kept, "entries": [1]}, {"text": dropped, "entries": [2]},
                ]},
                "rule_judgement": {"texts": [], "merged": []},
            }},
            "collapse": {target: {"entries": [
                {"piece": "p-0001", "text": kept},
                {"piece": "p-0002", "text": dropped},
            ]}},
        })
        (run / "coverage.json").write_text(json.dumps(state), encoding="utf-8")

        pending = subprocess.run(
            [sys.executable, str(COVER), "ask-owner", "--work", str(run)],
            check=True, capture_output=True, text=True,
        )
        assert pair_id in pending.stdout
        assert "which non-dropped duty, if any, survives" in pending.stdout
        answered = subprocess.run(
            [sys.executable, str(COVER), "answer-owner", "--work", str(run),
             "--id", pair_id, "--choice", "select-a", "--because", "retain only A"],
            check=True, capture_output=True, text=True,
        )
        assert "0 ruling(s) still pending" in answered.stdout
        output = Path(directory) / "requirements.md"
        subprocess.run(
            [sys.executable, str(COVER), "document", "--work", str(run), "--out", str(output)],
            check=True, capture_output=True, text=True,
        )
        text = output.read_text(encoding="utf-8")
        assert text.count(kept) == 1
        requirements_section = text.split("## Rejected, with reasons", 1)[0]
        assert dropped not in requirements_section
        history = json.loads((run / "coverage.json").read_text())["owner_rulings"][target][pair_id]
        assert history["history"][0]["choice"] == "keep-separate"


def test_reopened_selection_never_offers_an_alternate_dropped_side() -> None:
    target = "fixture requirements"
    side_a = "It applies from the first build and is checked at every gate. 1."
    side_b = ("These requirements apply to all documents, internal and client-facing, and are "
              "checked at every gate.")
    pair_id = "shared-rule-both-sides-dropped"
    pair_item = {
        "id": pair_id, "kind": "shared-rule",
        "question": "No validated shared rule could be extracted; which source duties survive?",
        "a": side_a, "b": side_b, "statement": f"A: {side_a}\nB: {side_b}",
        "pages": ["p-0001", "p-0002"],
        "choices": ["keep-both", "select-a", "select-b"],
    }
    dropped = {
        "check-1": {"item": {
            "id": "check-1", "kind": "checkability", "statement": side_a,
            "anchors": [side_a], "choices": ["keep", "drop", "split"],
        }, "choice": "drop"},
        "check-2": {"item": {
            "id": "check-2", "kind": "checkability", "statement": side_b,
            "anchors": [side_b], "choices": ["keep", "drop", "split"],
        }, "choice": "drop"},
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        state = bind_run_identity(run, {
            "strategy": "fixture", "opened_at": 0,
            "pieces": [
                {"id": "p-0001", "chars": 0, "sha256": ""},
                {"id": "p-0002", "chars": 0, "sha256": ""},
            ],
            "answers": {}, "relevance": {"target": target},
            "distilled": {target: {
                "items": [], "owner_pairs": [], "source_owner_pairs": [],
                "shared_rule_owner_records": [], "still_for_owner": [],
            }},
            "owner_rulings": {target: {
                **dropped,
                pair_id: {"item": pair_item, "choice": "select-b", "because": "prior"},
            }},
            "requirements": {target: {
                "rules_stage": {"rules": []},
                "rule_judgement": {"texts": [], "merged": []},
            }},
            "collapse": {target: {"entries": []}},
        })
        (run / "coverage.json").write_text(json.dumps(state), encoding="utf-8")

        pending = subprocess.run(
            [sys.executable, str(COVER), "ask-owner", "--work", str(run)],
            check=True, capture_output=True, text=True,
        )
        item = json.loads(pending.stdout)["item"]
        assert item["id"] == pair_id
        assert item["choices"] == ["drop-both"]

        answered = subprocess.run(
            [sys.executable, str(COVER), "answer-owner", "--work", str(run),
             "--id", pair_id, "--choice", "drop-both", "--because", "both were dropped"],
            check=True, capture_output=True, text=True,
        )
        assert "0 ruling(s) still pending" in answered.stdout
        complete = subprocess.run(
            [sys.executable, str(COVER), "ask-owner", "--work", str(run)],
            check=True, capture_output=True, text=True,
        )
        assert "nothing pending" in complete.stdout


def test_identical_selected_duties_materialize_once_with_combined_lineage() -> None:
    cover = load("requirements_cover_owner_materialization", COVER)
    reflow = load("requirements_reflow_owner_materialization", MACHINERY / "scripts" / "reflow.py")
    statement = "Preserve query logic and definitions so the research is repeatable."
    items = [
        {"statement": statement, "pages": ["p-0001"], "anchors": ["source A"],
         "how": "verbatim", "_kept_by_owner": "selected by first ruling"},
        {"statement": statement, "pages": ["p-0002"], "anchors": ["source B"],
         "how": "verbatim", "_kept_by_owner": "selected by second ruling"},
    ]

    result = cover._consolidate_kept_items(items, reflow)

    assert len(result) == 1
    assert result[0]["pages"] == ["p-0001", "p-0002"]
    assert result[0]["anchors"] == ["source A", "source B"]
    assert "first ruling" in result[0]["_kept_by_owner"]
    assert "second ruling" in result[0]["_kept_by_owner"]


def test_run_identity_is_immutable_and_detects_artifact_drift(capsys) -> None:
    cover = load("requirements_cover_run_identity", COVER)
    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        state = bind_run_identity(run, {
            "source": "fixture.pdf", "source_sha256": "a" * 64,
            "strategy": "fixture", "opened_at": 0,
            "pieces": [{"id": "p-0001", "chars": 0, "sha256": ""}],
            "answers": {},
        })
        state_path = run / "coverage.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        piece = run / "pieces" / "p-0001.txt"
        source = Path(state["source"])
        original_piece = piece.read_bytes()
        original_source = source.read_bytes()

        assert cover._read(run)["source_sha256"] == state["source_sha256"]

        piece.write_text("changed piece", encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "piece hash mismatch" in capsys.readouterr().err
        piece.write_bytes(original_piece)

        extra = run / "pieces" / "unregistered.txt"
        extra.write_text("extra", encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "unregistered piece file" in capsys.readouterr().err
        extra.unlink()

        piece.unlink()
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "missing piece file" in capsys.readouterr().err
        piece.write_bytes(original_piece)

        source.write_text("changed source", encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "source hash mismatch" in capsys.readouterr().err
        source.write_bytes(original_source)

        assert cover._read(run)["pieces"] == state["pieces"]

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "It never replaces existing state or a pieces directory" in contract
    assert "exact piece filename set" in contract


def test_empirical_claim_report_is_complete_and_tamper_evident() -> None:
    script_relative = Path("scripts") / "empirical_claims.py"
    manifest_relative = Path("evidence") / "empirical-claims.json"
    completed = subprocess.run([
        sys.executable, str(MACHINERY / script_relative), "validate",
        "--skill-root", str(MACHINERY),
    ], check=True, capture_output=True, text=True)
    report = json.loads(completed.stdout)
    assert report["status"] == "valid" and report["claims"] > 0
    assert report["missing"] == 0
    assert report["verified"] + report["unverified"] == report["claims"]

    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        copied = Path(directory) / "requirements-machinery"
        shutil.copytree(MACHINERY, copied, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        installed = subprocess.run([
            sys.executable, str(copied / script_relative), "validate",
            "--skill-root", str(copied),
        ], check=True, capture_output=True, text=True)
        assert json.loads(installed.stdout)["missing"] == 0
        skill = copied / "SKILL.md"
        original_skill = skill.read_text(encoding="utf-8")
        skill.write_text(original_skill.replace("Page won on", "Page won the", 1), encoding="utf-8")
        drift = subprocess.run([
            sys.executable, str(copied / script_relative), "validate",
            "--skill-root", str(copied),
        ], capture_output=True, text=True)
        assert drift.returncode == 3 and "claim inventory drift" in drift.stderr

        skill.write_text(original_skill, encoding="utf-8")
        manifest = copied / manifest_relative
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "Historical raw outputs", "Altered raw outputs", 1),
            encoding="utf-8",
        )
        tampered = subprocess.run([
            sys.executable, str(copied / script_relative), "validate",
            "--skill-root", str(copied),
        ], capture_output=True, text=True)
        assert tampered.returncode == 3 and "claim manifest hash mismatch" in tampered.stderr

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "An `unverified` disposition is not evidence" in contract


def test_work_path_guard_requires_nested_repository_containment() -> None:
    cover = load("requirements_cover_work_path", COVER)

    with pytest.raises(ValueError, match="repository root"):
        cover.validate_work_path(ROOT)
    resolved, repository = cover.validate_work_path(ROOT / "Tasks" / "future-run")
    assert repository == ROOT and ROOT in resolved.parents
    with pytest.raises(ValueError, match="temporary root"):
        cover.validate_work_path(Path("/tmp"))
    with pytest.raises(ValueError, match="recognized repository"):
        cover.validate_work_path(Path("/Users/kamenkamenov/rm14-nonrepository/run"))

    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        fake_worktree = Path(directory) / "worktree"
        fake_worktree.mkdir()
        (fake_worktree / ".git").write_text("gitdir: ../git-data\n", encoding="utf-8")
        child = fake_worktree / "Tasks" / "run"
        _, detected = cover.validate_work_path(child)
        assert detected == fake_worktree
        escape = Path(directory) / "escape"
        escape.symlink_to(Path("/Users/kamenkamenov/rm14-test-outside"), target_is_directory=True)
        with pytest.raises(ValueError, match="recognized repository"):
            cover.validate_work_path(escape / "child")

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "resolves symlinks and accepts only a nested path" in contract


def test_split_children_replay_full_checkability_and_refuse_tampering(capsys) -> None:
    cover = load("requirements_cover_split_checkability", COVER)
    target = "target requirements"
    anchor = (
        "The document must name one accountable owner for delivery; "
        "The document must state one measurable acceptance threshold"
    )

    class Interview:
        def __init__(self):
            self.calls = []
            self.checkability = iter([
                ["MAYBE", "YES"], ["YES"], ["YES"],
                ["YES"], ["NO"], ["YES"],
            ])

        def ask_choice(self, _reader, question, _choices, **context):
            raws = next(self.checkability) if "Could you write a check" in question else ["YES"]
            self.calls.append((question, list(raws), context))
            transcript, answer = [], None
            for attempt, raw in enumerate(raws, 1):
                accepted = raw if raw in {"YES", "NO"} else None
                row = {"attempt": attempt, "raw_first_line": raw, "accepted": accepted}
                if context.get("preserve_raw"):
                    row["raw_reply"] = raw
                transcript.append(row)
                if accepted:
                    answer = accepted
            return answer, transcript

    class Distill:
        @staticmethod
        def write_one(anchors, _reader, **_context):
            return anchors[0], [{"raw_reply": anchors[0]}]

    interview = Interview()
    distill = Distill()
    original_load = cover._load
    cover._load = lambda name: (
        interview if name == "interview" else distill if name == "distill" else original_load(name)
    )
    match = {
        "id": "check-1", "kind": "checkability", "statement": anchor,
        "pages": ["p-0001"], "choices": ["keep", "drop", "split"],
    }

    with tempfile.TemporaryDirectory(dir=ROOT / "Tasks") as directory:
        run = Path(directory) / "run"
        state = bind_run_identity(run, {
            "strategy": "fixture", "opened_at": 0,
            "pieces": [{"id": "p-0001", "chars": 0, "sha256": ""}],
            "answers": {},
            "distilled": {target: {"items": [{
                "pages": ["p-0001"], "statement": anchor, "how": "pen",
                "anchors": [anchor], "checkable": False,
            }]}},
        })
        assert cover._split_bundle(
            state, run, target, "check-1", match, "split", "separate duties", "fixture-reader"
        ) == 0

        persisted = json.loads((run / "coverage.json").read_text(encoding="utf-8"))
        parent = persisted["distilled"][target]["items"][0]
        children = [persisted["distilled"][target]["items"][index] for index in parent["split_into"]]
        split_graph = persisted["owner_rulings"][target]["check-1"]["split_graph"]
        assert len(children) == 2
        assert split_graph["parent_index"] == 0
        assert split_graph["child_indexes"] == parent["split_into"]
        assert len(split_graph["record_sha256"]) == 64
        assert all("checkability_record" in child for child in children)
        first_seat = children[0]["checkability_record"]["seats"][0]
        assert first_seat["raw_replies"] == ["MAYBE", "YES"]
        assert [row["reason"] for row in first_seat["validation"]] == ["malformed", "accepted"]
        assert children[0]["checkability_record"]["aggregate"][0]["disposition"] == "keep"
        assert children[1]["checkability_record"]["aggregate"][0]["disposition"] == "owner"

        calls_before_resume = len(interview.calls)
        assert cover._read(run)["distilled"][target]["items"] == persisted["distilled"][target]["items"]
        assert len(interview.calls) == calls_before_resume

        intact = copy.deepcopy(persisted)
        child_index = parent["split_into"][0]

        without_child_lineage = copy.deepcopy(intact)
        child = without_child_lineage["distilled"][target]["items"][child_index]
        child.pop("split_from")
        child.pop("checkability_record")
        (run / "coverage.json").write_text(json.dumps(without_child_lineage), encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "lineage marker disagrees" in capsys.readouterr().err
        assert len(interview.calls) == calls_before_resume

        without_statement = copy.deepcopy(intact)
        child = without_statement["distilled"][target]["items"][child_index]
        child["statement"] = ""
        child.pop("checkability_record")
        (run / "coverage.json").write_text(json.dumps(without_statement), encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "has no statement" in capsys.readouterr().err
        assert len(interview.calls) == calls_before_resume

        without_parent_link = copy.deepcopy(intact)
        without_parent_link["distilled"][target]["items"][0]["split_into"] = []
        (run / "coverage.json").write_text(json.dumps(without_parent_link), encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "parent links disagree" in capsys.readouterr().err
        assert len(interview.calls) == calls_before_resume

        without_graph = copy.deepcopy(intact)
        without_graph["owner_rulings"][target]["check-1"].pop("split_graph")
        (run / "coverage.json").write_text(json.dumps(without_graph), encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "has no integrity-bound graph" in capsys.readouterr().err
        assert len(interview.calls) == calls_before_resume

        original_record = intact["distilled"][target]["items"][child_index][
            "checkability_record"
        ]
        missing_seat = copy.deepcopy(original_record)
        missing_seat["seats"].pop()
        bad_aggregate = copy.deepcopy(original_record)
        bad_aggregate["aggregate"] = {}
        wrong_raw_type = copy.deepcopy(original_record)
        wrong_raw_type["seats"][0]["raw_replies"] = [1]
        malformed_records = [
            (None, "has no checkability record"),
            ("corrupt", "has no checkability record"),
            ([], "has no checkability record"),
            (missing_seat, "exactly three persisted seats"),
            (bad_aggregate, "aggregate must contain exactly one item"),
            (wrong_raw_type, "raw_replies must be a nonempty text list"),
        ]
        for malformed_record, expected_error in malformed_records:
            malformed_state = copy.deepcopy(intact)
            malformed_state["distilled"][target]["items"][child_index][
                "checkability_record"
            ] = malformed_record
            (run / "coverage.json").write_text(json.dumps(malformed_state), encoding="utf-8")
            with pytest.raises(cover.Refused):
                cover._read(run)
            error = capsys.readouterr().err
            assert "split child 2" in error
            assert expected_error in error
            assert len(interview.calls) == calls_before_resume

        tampered_evidence = copy.deepcopy(intact)
        tampered_evidence["distilled"][target]["items"][child_index][
            "checkability_record"
        ]["seats"][0]["raw_replies"][0] = "NO"
        (run / "coverage.json").write_text(json.dumps(tampered_evidence), encoding="utf-8")
        with pytest.raises(cover.Refused):
            cover._read(run)
        assert "split-child checkability evidence" in capsys.readouterr().err
        assert len(interview.calls) == calls_before_resume

    contract = (MACHINERY / "SKILL.md").read_text(encoding="utf-8")
    assert "every full raw attempt" in contract
    assert "Every resumed command replays all split-child" in contract
    assert "the graph before it can spend a reader" in contract
