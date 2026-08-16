#!/usr/bin/env python3
"""Take the next thing off the build order, have it built, and decide whether it is really done.

Everything before this step decided *what* to build and *in what order*. This one changes the
built system, and it is the first step in this machinery whose output is not a document. So it is
also the first that can quietly do damage, and the gates are shaped around that.

Three of them, in this order:

**What passes now.** The built system's tests are run *before* the change and the failures are
written down. On the subject this was built against, eight tests already failed for reasons that
have nothing to do with the work — so "all tests pass" would have refused every change forever,
and "the tests ran" would have accepted a change that broke twenty. The gate is neither: nothing
that passed before may fail after. That is the question a person actually cares about.

**The parts, answered again.** The requirements machinery already asked whether each part is true
of the built system and recorded 'no'. After the change, two readers who cannot see each other are
asked the same question against the changed code, and each 'yes' must quote the line it rests on.
A change that convinces one reader is not done.

**One thing at a time.** The builder is given one requirement, its parts, and nothing else. It may
not fix what it notices in passing: an unrelated repair inside this change makes it impossible to
say which edit made the part true, and the next run inherits the confusion.

Usage:
    python3 build_next.py --order <order.json> --work <dir> --built <repo> --tests '<command>'

Prints what is outstanding for the current item, or the verdict when it is finished. Run it,
do what it hands back, run it again.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True

from client_model_policy import validate_reader_command

PASSES = 2

#: How many times one item may be handed back to a builder before it goes to a person. A refusal is
#: information, not failure — the first item refused here was refused rightly, and a machinery with
#: no second attempt would have stalled on it. But an item that cannot be made true in three tries
#: is telling us something the builder cannot fix by trying again.
ATTEMPTS = 3

#: How long a reader that has already written its answer is given to close itself.
GRACE_SECONDS = 20

#: A copied source head-start must stay smaller than the work instruction around it. The first
#: experiment copied an entire enclosing function; on the captured r211 item that would have added
#: 41,567 characters, turning navigation help into another document to read.
BODY_CHAR_LIMIT = 8_000

#: Navigation must be smaller than the source it replaces and must never silently imply that a
#: clipped search was complete.  The captured r214 reader packet carried 15,274 characters of
#: definition names while still omitting the three places its stale citation matched.
NAVIGATION_CHAR_LIMIT = 12_000
NAVIGATION_MATCH_LIMIT = 12
NAVIGATION_REFERENCE_LIMIT = 24

_NAVIGATION_SKIP_DIRS = {
    ".git", ".mypy_cache", ".plan-playbook", ".pytest_cache", ".ruff_cache", ".tox",
    ".venv", "Tasks", "__pycache__", "build", "continuation-input", "dist",
    "node_modules", "operations", "proposed-revisions", "site-packages", "snapshots",
    "source-snapshots",
}

#: A malformed reader record is a delivery problem, not a product verdict. Give that seat one
#: clean correction before handing it to a person; never turn it into another build attempt.
RECORD_REPAIR_ATTEMPTS = 1

CONTROL_ROOT_ENV = "IMPLEMENTATION_MACHINE_CONTROL_ROOT"


def _control_root(work: Path) -> Path:
    """State a repository worker cannot author, keyed to this exact machinery run."""

    configured = os.environ.get(CONTROL_ROOT_ENV)
    root = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state" / "implementation-machine"
    )
    work_key = hashlib.sha256(str(work.resolve()).encode("utf-8")).hexdigest()
    return root.resolve() / work_key


def _control_record_path(work: Path, rid: str, name: str) -> Path:
    return _control_root(work) / "items" / rid / name


def _write_json_bytes(path: Path, payload: object) -> bytes:
    encoded = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return encoded


def _write_controller_record(
    work: Path, rid: str, public: Path, payload: object,
) -> object:
    """Write authority outside the worker workspace, then its inspectable projection."""

    authority = _control_record_path(work, rid, public.name)
    if public.is_file() and not authority.is_file():
        _preserve_untrusted_projection(work, rid, public, public.read_bytes())
    encoded = _write_json_bytes(authority, payload)
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_bytes(encoded)
    return payload


def _adopt_controller_record(
    work: Path, rid: str, public: Path, payload: object,
) -> object:
    """One-time migration of a record created before protected authority existed."""

    authority = _control_record_path(work, rid, public.name)
    encoded = _write_json_bytes(authority, payload)
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_bytes(encoded)
    return payload


def _preserve_untrusted_projection(
    work: Path, rid: str, public: Path, public_bytes: bytes,
) -> None:
    digest = hashlib.sha256(public_bytes).hexdigest()
    violation = _control_root(work) / "violations" / (
        f"{rid}-{public.name}-{digest}.json"
    )
    violation.parent.mkdir(parents=True, exist_ok=True)
    if not violation.exists():
        violation.write_bytes(public_bytes)


def _restore_controller_projection(
    work: Path, rid: str, public: Path, trusted_bytes: bytes,
) -> None:
    public_bytes = public.read_bytes() if public.is_file() else b""
    if public_bytes == trusted_bytes:
        return
    if public_bytes:
        _preserve_untrusted_projection(work, rid, public, public_bytes)
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_bytes(trusted_bytes)
    say(work, "controller record restored", item=rid, record=public.name)


def _read_controller_record(
    work: Path, rid: str, public: Path,
) -> object | None:
    authority = _control_record_path(work, rid, public.name)
    if not authority.is_file():
        if public.is_file():
            _preserve_untrusted_projection(work, rid, public, public.read_bytes())
            public.unlink()
            say(work, "untrusted controller record removed", item=rid, record=public.name)
        return None
    trusted_bytes = authority.read_bytes()
    trusted = json.loads(trusted_bytes.decode("utf-8"))
    _restore_controller_projection(work, rid, public, trusted_bytes)
    return trusted


def _valid_test_record(record: object, tests: str) -> bool:
    return (
        isinstance(record, dict)
        and record.get("command") == tests
        and isinstance(record.get("exit_code"), int)
        and isinstance(record.get("failed"), list)
        and isinstance(record.get("names"), list)
    )


def _read_controller_test_record(
    work: Path, rid: str, public: Path, tests: str,
) -> dict[str, object] | None:
    """Read only controller authority; preserve and replace any worker-written projection."""

    authority = _control_record_path(work, rid, public.name)
    if not authority.is_file():
        if not public.is_file():
            return None
        legacy = json.loads(public.read_text(encoding="utf-8"))
        if not _valid_test_record(legacy, tests):
            raise ValueError(
                f"controller_record_untrusted:{public}: expected command, exit_code, failed, names"
            )
        _adopt_controller_record(work, rid, public, legacy)
        return legacy

    trusted_bytes = authority.read_bytes()
    trusted = json.loads(trusted_bytes.decode("utf-8"))
    if not _valid_test_record(trusted, tests):
        raise ValueError(f"controller_record_invalid:{authority}")
    _restore_controller_projection(work, rid, public, trusted_bytes)
    return trusted


def _valid_done_record(record: object, rid: str) -> bool:
    common = (
        isinstance(record, dict)
        and record.get("item") == rid
        and record.get("built") is True
        and isinstance(record.get("parts_both_readers_call_true"), list)
        and not record.get("parts_not_agreed")
        and not record.get("parts_no_reader_answered")
        and not record.get("answers_under_a_name_no_part_has")
    )
    if not common:
        return False
    if "test_command_exit_code" in record:
        return (
            record.get("test_command_exit_code") == 0
            and not record.get("reader_citation_errors")
            and not record.get("test_removals_needing_owner")
        )
    # Protected authority may contain a receipt migrated from the machinery's earlier schema.
    # Bootstrap admits that schema only after `_valid_legacy_done_evidence` proves the controller's
    # original before/after and two-reader records.  Once adopted, this branch merely permits that
    # already-protected receipt to remain readable; workers cannot create protected authority.
    return not record.get("tests_that_broke")


def _valid_legacy_done_evidence(
    item: dict[str, object], work: Path, tests: str, record: object,
) -> bool:
    """Prove a pre-protection receipt by the acceptance artifacts its release produced."""

    rid = str(item["requirement_id"])
    if (
        not _valid_done_record(record, rid)
        or not isinstance(record, dict)
        or "test_command_exit_code" in record
    ):
        return False
    wanted = {str(part["part_id"]) for part in item["parts"]}
    if set(map(str, record["parts_both_readers_call_true"])) != wanted:
        return False

    out = work / f"build-{rid}"
    try:
        before = json.loads((out / "tests-before.json").read_text(encoding="utf-8"))
        after = json.loads((out / "tests-after.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for test_record in (before, after):
        if not (
            isinstance(test_record, dict)
            and test_record.get("command") == tests
            and isinstance(test_record.get("exit_code"), int)
            and isinstance(test_record.get("failed"), list)
        ):
            return False
    if set(map(str, after["failed"])) - set(map(str, before["failed"])):
        return False

    for index in range(1, PASSES + 1):
        answers = [
            answer for _, answer in _records_in(work / f"check-{rid}-{index}")
            if isinstance(answer, dict)
        ]
        by_part = {
            str(answer.get("part_id")): str(answer.get("answer")) for answer in answers
        }
        if set(by_part) != wanted or any(answer != "yes" for answer in by_part.values()):
            return False
    return True


def _valid_refused_record(record: object, rid: str) -> bool:
    return (
        isinstance(record, dict)
        and record.get("item") == rid
        and record.get("built") is False
        and isinstance(record.get("attempt"), int)
    )


def _bootstrap_controller_state(
    order: dict[str, object], work: Path, tests: str,
) -> None:
    """Bind pre-install completed receipts once; later repository writes gain no authority."""

    marker = _control_root(work) / "bootstrap.json"
    if marker.is_file():
        return
    adopted = []
    for item in order["work"]:
        rid = str(item["requirement_id"])
        public = work / f"build-{rid}" / "done.json"
        if public.is_file():
            record = json.loads(public.read_text(encoding="utf-8"))
            valid = _valid_done_record(record, rid)
            if valid and "test_command_exit_code" not in record:
                valid = _valid_legacy_done_evidence(item, work, tests, record)
            if not valid:
                raise ValueError(f"controller_done_record_untrusted:{public}")
            _adopt_controller_record(work, rid, public, record)
            adopted.append(rid)
        for refusal in (work / f"build-{rid}").glob("refused-*.json"):
            record = json.loads(refusal.read_text(encoding="utf-8"))
            if not _valid_refused_record(record, rid):
                raise ValueError(f"controller_refused_record_untrusted:{refusal}")
            _adopt_controller_record(work, rid, refusal, record)
    _write_json_bytes(marker, {"adopted_done_items": sorted(adopted)})


def _controller_refused_paths(work: Path, rid: str, out: Path) -> list[Path]:
    authority_dir = _control_record_path(work, rid, "placeholder").parent
    authoritative = {path.name for path in authority_dir.glob("refused-*.json")}
    for public in out.glob("refused-*.json"):
        if public.name in authoritative:
            continue
        _preserve_untrusted_projection(work, rid, public, public.read_bytes())
        public.unlink()
        say(work, "untrusted controller record removed", item=rid, record=public.name)
    restored = []
    for name in authoritative:
        public = out / name
        record = _read_controller_record(work, rid, public)
        if not _valid_refused_record(record, rid):
            raise ValueError(f"controller_refused_record_invalid:{public}")
        restored.append(public)
    return sorted(restored, key=lambda path: int(path.stem.rsplit("-", 1)[-1]))


def _test_symbol_keys(snapshot: object) -> set[str]:
    if not isinstance(snapshot, dict):
        return set()
    found = set()
    for relative, symbols in snapshot.items():
        if not str(relative).startswith("tests/") or not isinstance(symbols, dict):
            continue
        found.update(
            f"{relative}::{name}"
            for name in symbols
            if str(name).rsplit(".", 1)[-1].startswith("test_")
        )
    return found


def recover_clean_baseline(
    order: dict[str, object], work: Path, built: Path, tests: str, rid: str,
) -> dict[str, object]:
    """Recover a clean baseline only from evidence captured before the worker launch."""

    if not any(str(item["requirement_id"]) == rid for item in order["work"]):
        raise ValueError(f"baseline_recovery_unknown_item:{rid}")
    out = work / f"build-{rid}"
    public = out / "tests-before.json"
    authority = _control_record_path(work, rid, public.name)
    if authority.is_file():
        raise ValueError(f"baseline_recovery_authority_already_exists:{rid}")
    if not public.is_file():
        raise ValueError(f"baseline_recovery_missing_projection:{rid}")
    projected = json.loads(public.read_text(encoding="utf-8"))
    if (
        not isinstance(projected, dict)
        or projected.get("command") != tests
        or projected.get("exit_code") != 0
    ):
        raise ValueError(f"baseline_recovery_projection_not_clean:{rid}")

    events = [
        json.loads(line)
        for line in (work / "feed.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    clean_index = next(
        (
            index for index, event in enumerate(events)
            if event.get("what") == "tests before the change read"
            and event.get("item") == rid
            and event.get("already_failing") == 0
        ),
        None,
    )
    launched_after = (
        clean_index is not None
        and any(
            event.get("what") == "agent started"
            and event.get("waiting_for") == f"build-{rid}"
            for event in events[clean_index + 1:]
        )
    )
    if not launched_after:
        raise ValueError(f"baseline_recovery_missing_prechange_evidence:{rid}")

    before_path = out / "navigation-before.json"
    if not before_path.is_file():
        raise ValueError(f"baseline_recovery_missing_before_image:{rid}")
    before_symbols = _test_symbol_keys(json.loads(before_path.read_text(encoding="utf-8")))
    current_symbols = _test_symbol_keys(_symbol_snapshot(built))
    disappeared = sorted(before_symbols - current_symbols)
    if disappeared:
        raise ValueError(
            "baseline_recovery_test_identity_disappeared:" + ",".join(disappeared)
        )

    with _timed(work, "recovering clean baseline", item=rid):
        recovered = _failures(built, tests)
    if recovered.get("exit_code") != 0 or recovered.get("failed"):
        raise ValueError(f"baseline_recovery_current_tests_not_clean:{rid}")
    if not _valid_test_record(recovered, tests):
        raise ValueError(f"baseline_recovery_current_record_invalid:{rid}")
    recovered["recovery"] = {
        "prechange_failures": 0,
        "preexisting_test_identities": len(before_symbols),
        "disappeared_test_identities": [],
        "source": "controller feed plus neutral pre-builder symbol snapshot",
    }
    _write_controller_record(work, rid, public, recovered)
    _write_json_bytes(
        _control_record_path(work, rid, "baseline-recovery.json"),
        recovered["recovery"],
    )
    say(work, "clean baseline recovered", item=rid, tests=len(recovered["names"]))
    return recovered

#: An unattended builder cannot stop to ask the person who already approved the machinery run.
#: This text is added only when the launcher makes that approval explicit on the command line;
#: without the flag, the packet makes no authority claim.  It relays the bounded authority rather
#: than widening it, and keeps commit/deploy/destructive boundaries with the person driving.
OWNER_APPROVED = (
    "\n\nAuthority for this item. The owner explicitly approved this Implementation Machinery "
    "run to make only the product and test edits required to make the requirement above true, "
    "to run the prescribed verification, and to write the named machinery records. Treat that "
    "as the approved bounded code-change envelope; do not stop to ask again for those in-scope "
    "actions. It does not authorize unrelated edits, commits, pushes, deployments, destructive "
    "actions, credentials, external messages, or work outside the system and machinery paths "
    "named in this instruction."
)

#: Said when the owner has ruled on something the builder would otherwise be right to refuse.
#: The first item to need this was one where three committed tests required the very behaviour the
#: requirement forbade. The builder was correct to stop — a test is somebody's recorded intent, and
#: a builder that rewrites tests to agree with itself proves nothing. But when the owner has since
#: ruled which side is wrong, that ruling has to reach the builder through the machinery, or it
#: travels in whatever the driver happens to type, which is the seam this machinery exists to close.
RULED = (
    "\n\nThe owner has ruled on this item, in these words:\n\n{ruling}\n\nThat ruling settles "
    "what the system should do. Where an existing test requires the behaviour the ruling forbids, "
    "that test is now wrong and you may change it — say exactly which tests you changed and why in "
    "'what_changed'. Nothing else about the rules above changes."
)

RULING_FOR_READER = (
    "\n\nThe owner has settled an ambiguity in this item, in these exact words:\n\n"
    "{ruling}\n\nTreat that as the authoritative meaning of the requirement while judging the "
    "current system. It is owner input, not the builder's conclusion and not another reader's "
    "answer; your reading must still be independent."
)

#: Said when a previous attempt was refused. The objection is quoted rather than summarised: on the
#: refusal that made this necessary, the readers' own words — that the change marks the sentence and
#: a mark stops nothing — were the whole content of what had to change.
AGAIN = (
    "\n\nAn earlier attempt at this was refused. What it changed: {what_changed}\n\nWhy the "
    "readers refused it, in their words:\n{objections}\n\nThat earlier change is still in the "
    "system. Decide for yourself whether to build on it, narrow it, or take it out — but the "
    "sentences above must end up true, and the objection above must no longer hold."
)

#: The change itself. It says what must become true, never how — the how is the builder's judgement
#: against the code in front of it, and a machinery that dictates the edit is just a slower author.
BUILD = (
    "In the system at {built}, make this true: {requirement}\n\nIt is true when all of these are "
    "true:\n{parts}\n\nRules. Change as little as possible, and change nothing that is not needed "
    "for the sentences above — if you notice something else wrong, leave it and say so at the end, "
    "because a repair mixed into this change makes it impossible to tell which edit made the part "
    "true. When an existing test contradicts the sentences above, the sentences win and the test "
    "is now wrong: change it, and say in 'what_changed' exactly which test you changed and what it "
    "used to assert. The tests record how this system behaved; the sentences record how its owner "
    "says it must behave, and they are the newer statement. This is not licence to make a failing "
    "test pass — never weaken or delete a test that is about something else, and never touch one "
    "the sentences do not reach. Do not go through the history — no log, no blame, no diff against "
    "an earlier commit. When something changed tells you nothing about whether it is right, and a "
    "builder that asks it spends its time there: on the job that made this rule, four separate "
    "stretches went to history and none of them moved the work. What decides it is the code as it "
    "stands and the check that fails; run that check, read what it exercises, and find the cause "
    "there. When you are done, write {out}/change.json holding "
    "{{'files': ['<path you changed>', ...], 'what_changed': '<a few sentences a person can "
    "read>', 'tests_changed': [{{'test': '<its name>', 'used_to_assert': '<what it said before>', "
    "'why': '<the sentence above that it contradicted>'}}], "
    "'left_alone': '<anything you noticed and did not touch>'}}."
)

PROTECTED_TEST_IDENTITIES = (
    "\n\nProtected test identities. The controller recorded {count} pre-existing collected test "
    "names in {path}. Before renaming or removing a test, read that file. You may change what an "
    "existing test asserts when the requirement makes its old assertion wrong, but keep its exact "
    "collected identity and make that same entry point exercise the required behavior. Only an "
    "exact owner ruling can authorize removing one. The controller checks this before either blind "
    "reader starts and returns every missing identity to you for correction."
)

#: Where the readers looked when they said this was not true yet. It is a starting point and not an
#: instruction: a reader can cite the right file and still have missed the place that decides it,
#: so the builder is told to check rather than trust, and told plainly that it may end up elsewhere.
SEEN_AT = (
    "\n\nWhen this was judged not yet true, the readers cited these places:\n{seen_at}\n\nStart "
    "there. They are where somebody looked, not where the answer must be — confirm each one says "
    "what it is quoted as saying, and if the place that actually decides the sentence is somewhere "
    "else, go there and say so in 'what_changed'."
)

#: What is in the files this job touches. Handed over so the builder can go to a place instead of
#: searching for it.
MAP = (
    "\n\nMechanical structural starting points, so you can go straight to the cited candidates, "
    "their consumers and focused tests rather than reading whole files:\n\n{map}\n\nThe map "
    "contains no verdict. Expand beyond it wherever the requirement is actually decided.\n"
)

#: The reading that decides it. Deliberately the same question the requirements machinery asked, so
#: a 'yes' here is comparable with the 'no' that put this on the list in the first place.
VERIFY = (
    "For each of these sentences, answer whether it is true of the system at {built} right now. "
    "Each one is given with the name it must be answered under, and that name must come back "
    "exactly as written — the first time this step ran, two readers answered the same sentence "
    "under two different names, and the gate that counts one answer per reader could not tell it "
    "had only heard from one of them:\n{named_parts}\n\nWrite one file per sentence into {out}: "
    "{{'part_id','answer':'yes'|'no','citations':[{{'where':'<absolute file path>','line':<number>,"
    "'text':'<that line, exactly>'}}],'looked_at':'<what you read and where>'}}. A 'yes' carries at "
    "least one citation whose text is that line character for character; a 'no' says what you "
    "looked at and names the nearest thing to it in the system. Read the built system, nothing else."
)

#: How this system's tests are run. The machinery is given the command on the command line and then
#: kept it to itself, so every agent it starts began by working out how to run a test: `which
#: python3`, `ls .venv`, `which uv`, a pytest that fails on the wrong interpreter, then a second
#: one that works. Across three agents an item — a builder and two checkers — that is half a minute
#: an item spent rediscovering a fact the machinery already had in a variable.
REPOSITORY_CONTEXT = (
    "Repository root: {built}\n"
    "Full test command: {tests}\n"
    "Output directory: {out}\n"
    "Scratch directory: {scratch}\n\n"
    "Run commands from the repository root. To run less than the full suite, keep the supplied "
    "test command and append paths or names. Do not search for another interpreter, environment, "
    "or test runner: this is the prepared repository context."
)

BLIND = (
    " You are one of two independent readers of this same question: do not open any sibling output "
    "or scratch directory, and do not look for what the other found. Agreement between two readers "
    "who could not see each other is the only evidence this machinery accepts."
)

HOW_TO_READ = (
    # Measured, not guessed: across nine agents in two runs, each one opened the working agreement
    # four or five times in its first twenty seconds — a pointer file two directories above the
    # repository sends it there, and the agreement is long enough to need several reads. That is
    # about a minute an item across a builder and two checkers, and none of it is about the item.
    # The agreement governs whoever is driving this machinery; it does not govern the workers,
    # whose whole brief is the instruction above.
    " The system you are working on is the one directory you were given. Do not go looking outside "
    "it for the machinery that started you — not its work directory, not its order file, not its "
    "other items' records, not its source. Three builders spent between forty seconds and two "
    "minutes each doing exactly that on 2026-08-11, listing the scratch directory and searching the "
    "home directory for the tool's own folders, and none of them learnt anything: the requirement, "
    "the part and the place to look are already in this instruction, and nothing over there is "
    "about your item."
    " This instruction is your entire brief. Do not go and read a working agreement, a directives "
    "file, a CLAUDE.md or any other standing-instructions document, and do not follow a pointer "
    "to one: they govern whoever started you, not the job you were given, and nothing in them "
    "changes what this asks of you or what you must write. "
    " Write files as you go so progress is visible; a reader that writes nothing until the end "
    "cannot be told apart from one that has stopped. Put every working, scratch or intermediate "
    "file in {scratch} and nowhere else — that directory is yours alone. Before you finish, write "
    "{scratch}/reader.json holding {{'model': '<the model you are, as you are identified>', "
    "'harness': '<the tool you are running inside>'}}. This machinery never chooses a reader — "
    "whoever runs it supplies one, so the record has to say who did the reading."
)


def _test_inventory(built: Path, tests: str) -> dict[str, object]:
    """Collect test identities with the command status needed for a safe early comparison."""

    done = subprocess.run(f"{tests} --collect-only", shell=True, cwd=str(built),
                          capture_output=True, text=True, check=False)
    output = done.stdout + done.stderr
    return {
        "exit_code": done.returncode,
        "names": sorted({
            line.strip() for line in done.stdout.splitlines() if "::" in line
        }),
        "tail": output.strip().splitlines()[-1:] or [""],
    }


def _test_names(built: Path, tests: str) -> list[str]:
    """Which tests exist right now, by name, asked of the same runner that runs them.

    The gate is that nothing which passed before may fail now, and a deleted test satisfies it
    without effort. A builder reports which tests it changed, and nothing could check that report:
    on 2026-08-11 two tests had gone from one file, one of them declared with its reason and one
    of them not, and the difference was only found by reading the file by hand. Collecting the
    names either side of a build makes a disappearance a fact in the record instead of something
    somebody has to happen to notice. It decides nothing — a test may be replaced by a stricter
    one, and often should be — it only refuses to let the removal be silent.
    """

    return list(_test_inventory(built, tests)["names"])


def _repository_state(built: Path, work: Path) -> dict[str, list[int]] | None:
    """What is uncommitted in the built system right now, by size and modification time.

    Which files an item changed was the builder's own sentence about itself, and nothing ever
    compared it with the repository. On 2026-08-15 a batch's builders named 37 files where 44 had
    to move for the suite to pass; on 2026-08-16 they named 21 where the true number was 43, and a
    clean copy of the repository carrying only the named files failed 67 tests. The same list is
    what both blind readers are told changed, so an incomplete one narrows the evidence they judge
    against. Version control already knows what moved and cannot be mistaken about its own
    repository, so the record asks it instead of asking the worker. `None` means the built system
    keeps no version control here and the claim is all there is — which the record then says.
    """

    listed = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
        cwd=str(built), capture_output=True, text=True, check=False,
    )
    if listed.returncode != 0:
        return None
    try:
        inside = work.resolve().relative_to(built.resolve()).as_posix()
    except ValueError:
        inside = ""
    rows = iter([row for row in listed.stdout.split("\0") if row])
    state: dict[str, list[int]] = {}
    for row in rows:
        if len(row) < 4:
            continue
        status, name = row[:2], row[3:]
        # A rename carries its old path in the next field; it is not a change of its own.
        if "R" in status or "C" in status:
            next(rows, None)
        if inside and (name == inside or name.startswith(inside + "/")):
            continue
        try:
            info = (built / name).stat()
        except OSError:
            state[name] = []
            continue
        state[name] = [info.st_size, info.st_mtime_ns]
    return state


def _moved(before: dict[str, object], after: dict[str, object]) -> list[str]:
    return sorted({
        name for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    })


def _directories_above(name: str) -> list[str]:
    parts = Path(name).parts[:-1]
    return [Path(*parts[:depth + 1]).as_posix() for depth in range(len(parts))]


def _what_running_the_tests_writes(
    before: dict[str, object], after: dict[str, object],
) -> dict[str, list[str]]:
    """What moves when the tests run and nothing has been built yet.

    The built system's own suite writes files as it runs — caches, packaging metadata, captured
    run artifacts under names that differ every time. Those are moved by the builder too, because
    the builder runs the tests, and counting them as the change would bury the four real files
    under thirty thousand. Watching the baseline run, which happens anyway before anything is
    touched, says which paths and which directories that is without anybody deciding it.
    """

    moved = _moved(before, after)
    appeared = [name for name in moved if name not in before]
    return {
        "paths": moved,
        "directories": sorted({
            directory for name in appeared
            for directory in _directories_above(name) if directory not in (".", "")
        }),
    }


def _what_the_builder_moved(
    before: dict[str, object], after: dict[str, object], noise: dict[str, object],
) -> list[str]:
    quiet_paths = set(noise.get("paths") or [])
    quiet_directories = tuple(str(row) for row in (noise.get("directories") or []))
    kept = []
    for name in _moved(before, after):
        if name in quiet_paths:
            continue
        if name not in before and any(
            name.startswith(directory + "/") for directory in quiet_directories
        ):
            continue
        kept.append(name)
    return kept


def _reconcile_with_the_repository(
    work: Path, rid: str, out: Path, built: Path, change_path: Path, attempt: int,
) -> dict[str, object]:
    """The change the repository shows, beside the change the builder says it made.

    Settled once per **attempt**, the first time that attempt's delivery is seen, and kept: the
    readers run the tests after this point and would otherwise move the ground under it. It is per
    attempt because the first version of this settled once per item, and on 2026-08-16 r100's
    second builder wrote forty-eight lines into the engine, declared no files, and was refused for
    changing nothing — the step had reused the first attempt's "nothing moved" and could not see
    the change sitting in the tree. The before-image stays the item's first one, so the accepted
    attempt's list still names everything that moved since the item was taken up, including work an
    earlier refused attempt left behind. What the builder claimed is kept too, and the difference
    is a fact in the record rather than something a person finds later by cloning the repository
    and watching the suite fail.
    """

    change = json.loads(change_path.read_text(encoding="utf-8"))
    claimed = sorted({
        _source_label(built, path if (path := Path(str(name))).is_absolute() else built / name)
        for name in (change.get("files") or []) if str(name).strip()
    })
    observed_path = out / f"files-observed-{attempt}.json"
    settled = _read_controller_record(work, rid, observed_path)
    if not isinstance(settled, dict):
        started = _read_controller_record(work, rid, out / "files-before.json")
        now = _repository_state(built, work)
        if not isinstance(started, dict) or now is None:
            change["files"] = claimed
            change["builder_said_changed"] = claimed
            change["repository_watched"] = False
            return change
        noise = _read_controller_record(work, rid, out / "files-the-tests-write.json")
        moved = _what_the_builder_moved(
            started, now, noise if isinstance(noise, dict) else {},
        )
        settled = {
            # The union, never the intersection: a file either of them names is evidence, and
            # narrowing what the two blind readers are shown is the failure this exists to end.
            "files": sorted(set(moved) | set(claimed)),
            "builder_said_changed": claimed,
            "changed_without_saying_so": sorted(set(moved) - set(claimed)),
            "said_but_did_not_change": sorted(set(claimed) - set(moved)),
            "repository_watched": True,
        }
        _write_controller_record(work, rid, observed_path, settled)
        if settled["changed_without_saying_so"]:
            say(work, "the builder's file list was short", item=rid,
                said=len(claimed), moved=len(moved),
                without_saying_so=settled["changed_without_saying_so"][:20])
    change.update({key: value for key, value in settled.items()})
    return change


def _failures(built: Path, tests: str) -> dict[str, object]:
    """Run the built system's own tests and note which ones fail, in its own words."""

    done = subprocess.run(tests, shell=True, cwd=built, capture_output=True, text=True)
    output = done.stdout + done.stderr
    failed = sorted(set(re.findall(r"^FAILED (\S+)", output, re.M)))
    return {"command": tests, "exit_code": done.returncode, "failed": failed,
            "names": _test_names(built, tests),
            "tail": output.strip().splitlines()[-1:] or [""]}


def _readable(directory: Path) -> list[Path]:
    """Every file in a reader's output directory that actually holds a record.

    The machinery counted `*.json` by name. On 2026-08-11 a checker did the whole job — read the
    code, found the rule, cited the enforcing lines — and wrote its verdict as `r151.p2`, without
    the extension. It was counted as nothing, the seat was relaunched, and five minutes and forty
    seconds of correct reading were thrown away over a filename. A record is a record because it
    parses, not because of what it is called, and the whole point of the two readers is that their
    work is expensive to reproduce.
    """

    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.name == "reader.json":
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        found.append(path)
    return found


def _delivered(directory: Path, pattern: str) -> int:
    """What the packet asked for, not whatever else the directory happens to hold.

    The build packet writes into a directory that already carries the test baseline, so counting
    every file there made a builder look finished the moment it started. It was killed twenty
    seconds in, twice, and the run stopped with nothing built.
    """

    # A builder is asked for one named file, and the name is what protects it from the baseline
    # files already in that directory. A reader is asked for "whatever answers you wrote", and
    # there the name protects nothing and has cost real work — so count what parses instead.
    if pattern != "*.json":
        return len(list(directory.glob(pattern))) if directory.is_dir() else 0
    return len(_readable(directory))


def _answers_in(directory: Path) -> int:
    return len(_readable(directory))


def _packet(instruction: str, out: Path, scratch: Path, blind: bool,
            built: Path, tests: str,
            expect: int = 1, wants: str = "*.json",
            owner_approved: bool = False) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    stable = HOW_TO_READ.format(scratch=scratch)
    if blind:
        stable += BLIND
    authority = OWNER_APPROVED if owner_approved else ""
    assembled = (
        "## Stable worker directives\n\n" + stable.strip()
        + "\n\n## Repository context\n\n"
        + REPOSITORY_CONTEXT.format(
            built=built, tests=tests, out=out, scratch=scratch,
        )
        + ("\n\n## Authority\n\n" + authority.strip() if authority else "")
        + "\n\n## Item task\n\n" + instruction.strip()
    )
    return {"instruction": assembled,
            "waiting_for": str(out), "scratch": str(scratch),
            "expect": expect, "wants": wants}


def next_item(order: dict[str, object], work: Path) -> dict[str, object] | None:
    """The earliest round first, and inside a round the smallest piece of work."""

    for item in sorted(order["work"], key=lambda w: (w["round"], w["part_count"],
                                                     str(w["requirement_id"]))):
        rid = str(item["requirement_id"])
        public = work / f"build-{rid}" / "done.json"
        done = _read_controller_record(work, rid, public)
        if done is not None and not _valid_done_record(done, rid):
            raise ValueError(f"controller_done_record_invalid:{public}")
        if done is None:
            return item
    return None


#: What a streamed tool event is worth saying. A tool's own arguments say more about what the agent
#: is doing than any summary of them would: the file it opened, the pattern it searched for, the
#: command it ran. Anything longer than this is the agent's prose, and the prose is in its log.
def _what_it_did(event: dict[str, object]) -> str | None:
    # Codex `exec --json` streams item lifecycle events.  Keep this adapter beside the
    # older Claude stream adapter so each client retains its native command while the
    # machinery reports the same practical action.
    if str(event.get("type")) in {"item.started", "item.completed"}:
        item = event.get("item") or {}
        if not isinstance(item, dict):
            return None
        kind = str(item.get("type") or "item")
        said = (
            item.get("command")
            or item.get("tool")
            or item.get("name")
            or item.get("path")
            or item.get("text")
            or ""
        )
        return f"{kind} {_both_ends(str(said))}".strip()
    if str(event.get("type")) != "assistant":
        return None
    for block in (event.get("message") or {}).get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        used = block.get("input") or {}
        said = (used.get("file_path") or used.get("pattern") or used.get("command")
                or used.get("path") or used.get("query") or "")
        return f"{block.get('name')} {_both_ends(str(said))}".strip()
    return None


def _failure_it_reported(event: dict[str, object]) -> str | None:
    """A terminal child error in either supported streaming event format."""

    if str(event.get("type")) not in {"turn.failed", "error"}:
        return None
    error = event.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
    else:
        message = error
    message = message or event.get("message")
    return _both_ends(str(message), keep=500) if message else str(event.get("type"))


def _both_ends(said: str, keep: int = 120) -> str:
    """Keep the start and the end of a long command, never the start alone.

    Cutting at a fixed length reads fine until the paths are long. On 2026-08-11 every command an
    agent ran against its own work directory was recorded as the first hundred and twenty
    characters of a hundred-and-ten-character path: the feed said `Bash ls <path>/impl2/bui` over
    and over, and which item it was reading, and what it was looking for, were exactly the part
    that fell off. A watcher could see that the agent was busy and not what it was busy with,
    which is the one thing this feed exists to show. The end of a command carries the argument;
    the middle of a path carries almost nothing.
    """

    if len(said) <= keep:
        return said
    head = keep * 2 // 3
    return f"{said[:head]}…{said[-(keep - head):]}"


def _watch(
    stream, work: Path, job: str, captured: list[str], failures: list[str] | None = None,
) -> None:
    """Losslessly capture a child stream and report understood JSON events.

    This function is the sole reader of its pipe.  Every raw line is retained before
    interpretation, so an unknown or newly-added client event remains available in the launch
    log instead of disappearing merely because the live feed does not understand it yet.
    """

    for raw_line in stream:
        captured.append(raw_line)
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        did = _what_it_did(event)
        if did:
            say(work, "agent", job=job, doing=did)
        failed = _failure_it_reported(event)
        if failed:
            if failures is not None:
                failures.append(failed)
            say(work, "agent failure", job=job, error=failed)


def _drain(stream, captured: list[str]) -> None:
    """Drain one non-event child stream without risking pipe backpressure."""

    for raw_line in stream:
        captured.append(raw_line)


#: A definition, at the start of a line or one indent in. Deliberately crude: this is a map for
#: somebody who is going to open the file anyway, not an index anybody parses.
_DEFINED = re.compile(r"^(?: {4})?(?:async def |def |class )(\w+)")


def _body_at(built: Path, seen_at: str) -> str:
    """The definition that encloses a cited line, copied out whole.

    An experiment, not a settled part of the machinery, and it is here because the cheaper version
    of the same idea did not work. Builders are already handed a map of every definition in the
    cited file with its line number, added after one of them read the same five-thousand-line file
    six times. With that map in place they still spend seventy-two per cent of their minutes
    reading and searching, measured across thirty builders on 2026-08-11. So the question this
    answers is whether the map is too little — whether a builder handed the actual lines it has to
    change goes faster — and the only way to know is to run one item both ways.

    The block returned starts at the enclosing `def` or `class` above the cited line and ends where
    the indentation returns to that level. Nothing is judged: if the line cannot be found, or sits
    outside any definition, this returns nothing rather than guessing at a boundary.
    """

    match = re.match(r"^(.*?):(\d+) — (.*)$", seen_at, re.S)
    if not match:
        return ""
    where, line = match.group(1), int(match.group(2))
    path = Path(where) if Path(where).is_absolute() else built / where
    if not path.is_file() or path.suffix != ".py":
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 1 <= line <= len(lines):
        return ""
    raw_text = match.group(3).strip()
    if raw_text.endswith(","):
        raw_text = raw_text[:-1].rstrip()
    if raw_text.startswith('"') and raw_text.endswith('"'):
        try:
            cited_text = str(json.loads(raw_text))
        except (json.JSONDecodeError, ValueError):
            return ""
    else:
        cited_text = raw_text.strip('"')
    wanted = " ".join(cited_text.split()).lower()
    if not wanted:
        return ""
    if wanted not in " ".join(lines[line - 1].split()).lower():
        found = [
            number for number, row in enumerate(lines, start=1)
            if wanted in " ".join(row.split()).lower()
        ]
        if len(found) != 1:
            return ""
        line = found[0]
    start = next((n for n in range(line - 1, -1, -1) if _DEFINED.match(lines[n])), None)
    if start is None:
        return ""
    # The block ends where the next definition at this level begins, not where the indentation
    # first returns to it: a signature spread over several lines closes with `) -> X:` in column
    # zero, and the first version of this ended there, handing over five lines of arguments and
    # calling it the function.
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for n in range(start + 1, len(lines)):
        row = lines[n]
        if _DEFINED.match(row) and (len(row) - len(row.lstrip())) <= indent:
            end = n
            break
    full_label = f"{Path(where).name} lines {start + 1}-{end}:\n"
    complete = full_label + "\n".join(lines[start:end])
    if len(complete) <= BODY_CHAR_LIMIT:
        return complete

    # Keep the definition signature and a symmetric window around the cited line. Shrink one line
    # at a time until the rendered excerpt fits; if one source line alone is huge, clip only that
    # displayed excerpt. The original file remains the authority and the prompt says to re-open it.
    focus = line - 1
    low, high = max(start, focus - 32), min(end, focus + 33)
    label = (
        f"{Path(where).name} definition lines {start + 1}-{end}, "
        f"bounded excerpt around cited line {line}:\n"
    )

    def render() -> str:
        rows = [lines[start]]
        if low > start + 1:
            rows.append("    ...")
        rows.extend(lines[max(low, start + 1):high])
        if high < end:
            rows.append("    ...")
        return label + "\n".join(rows)

    excerpt = render()
    while len(excerpt) > BODY_CHAR_LIMIT and high - low > 1:
        if focus - low >= high - focus:
            low += 1
        else:
            high -= 1
        excerpt = render()
    if len(excerpt) > BODY_CHAR_LIMIT:
        # One source line can itself exceed the whole prompt budget. Keep the definition name and
        # a window around the cited text, rather than clipping from column zero and potentially
        # dropping the only reason this excerpt was included.
        prefix = label + lines[start] + "\n    …\n"
        focus_row = lines[focus]
        at = focus_row.lower().find(cited_text.lower())
        if at < 0:
            at = len(focus_row) // 2
        room = max(1, BODY_CHAR_LIMIT - len(prefix) - 3)
        left = max(0, at - room // 2)
        right = min(len(focus_row), left + room)
        left = max(0, right - room)
        excerpt = prefix + ("…" if left else "") + focus_row[left:right]
        if right < len(focus_row):
            excerpt += "…"
    return excerpt


#: The lines a cited place actually sits in. Only sent when the experiment flag is on, so a run
#: with it and a run without it differ in exactly this and nothing else.
BODY = (
    "\n\nThe lines each cited place sits in, copied out so you do not have to go and find "
    "them:\n\n{bodies}\n\nThis is what was there when this job started. Check it still says that "
    "before you rely on it, and read whatever else you need — it is a head start, not a boundary.\n"
)


UNIVERSAL_PREPARATION = (
    "\n\nThis requirement makes a universal claim. Before handing the change to the readers, "
    "trace the normal return, every retry or fallback/error return, and every post-validation "
    "transformation that runs after the enforcing check. Add a focused test for each materially different path the "
    "requirement reaches. Record those paths and tests in change.json under 'paths_checked'. This "
    "preparation is not acceptance evidence: the two blind readers and the machinery's test gate "
    "still decide whether the item is built.\n"
)

_UNIVERSAL = re.compile(r"\b(?:never|every|all|always)\b|\bmust\s+not\b", re.I)


def _universal_preparation(requirement: str) -> str:
    return UNIVERSAL_PREPARATION if _UNIVERSAL.search(requirement) else ""


READER_START = (
    "\n\nMechanical starting points, copied from the current source without a verdict:\n{places}"
    "{map}\nThese are starting points, not a boundary. Independently inspect the actual system, "
    "follow every path the sentence reaches, and expand beyond this map wherever the answer is "
    "decided. No builder conclusion or other reader output is included.\n"
)


RECORD_REPAIR = (
    "\n\nYour previous delivery could not be counted because its record contract was invalid:\n"
    "{errors}\nWrite the answer again under the exact part id and schema above. This is the same "
    "reader seat; do not open any sibling reader directory.\n"
)


def _source_label(built: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(built.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _python_files(built: Path) -> list[Path]:
    """Version-controlled Python sources; generated work must never steer a worker."""

    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        cwd=str(built),
        capture_output=True, text=True, check=False,
    )
    if tracked.returncode == 0:
        return sorted(
            built / name for name in tracked.stdout.split("\0")
            if name and (built / name).is_file()
            and not any(part in _NAVIGATION_SKIP_DIRS for part in Path(name).parts)
        )
    return sorted(
        path for path in built.rglob("*.py")
        if not any(
            part in _NAVIGATION_SKIP_DIRS or part in {"Tasks", "operations"}
            for part in path.relative_to(built).parts
        )
    )


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _SymbolVisitor(ast.NodeVisitor):
    """Collect source definitions and the calls made directly inside each definition."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.symbols: list[dict[str, object]] = []
        self.stack: list[dict[str, object]] = []

    def _definition(self, node: ast.AST, name: str, kind: str) -> None:
        prefix = str(self.stack[-1]["qualname"]) + "." if self.stack else ""
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start) or start)
        source = "\n".join(self.lines[start - 1:end])
        symbol: dict[str, object] = {
            "name": name,
            "qualname": prefix + name,
            "kind": kind,
            "line": start,
            "end_line": end,
            "hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "calls": [],
        }
        self.symbols.append(symbol)
        self.stack.append(symbol)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._definition(node, node.name, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._definition(node, node.name, "async function")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._definition(node, node.name, "class")

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _call_name(node.func)
        if self.stack and name:
            calls = self.stack[-1]["calls"]
            assert isinstance(calls, list)
            calls.append({"name": name, "line": int(node.lineno)})
        self.generic_visit(node)


def _symbols_in(path: Path) -> list[dict[str, object]]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, ValueError):
        return []
    visitor = _SymbolVisitor(source.splitlines())
    visitor.visit(tree)
    return visitor.symbols


def _symbol_index(built: Path) -> dict[str, list[dict[str, object]]]:
    return {
        _source_label(built, path): symbols
        for path in _python_files(built)
        if (symbols := _symbols_in(path))
    }


def _symbol_snapshot(built: Path) -> dict[str, dict[str, dict[str, object]]]:
    """A neutral before-image small enough to identify symbols changed by one builder."""

    return {
        path: {
            str(symbol["qualname"]): {
                "name": symbol["name"], "line": symbol["line"],
                "end_line": symbol["end_line"], "hash": symbol["hash"],
            }
            for symbol in symbols
        }
        for path, symbols in _symbol_index(built).items()
    }


def _citation(built: Path, seen_at: str) -> tuple[Path, int, str] | None:
    match = re.match(r"^(.*?):(\d+) — (.*)$", seen_at, re.S)
    if not match:
        return None
    where, line, raw = match.group(1), int(match.group(2)), match.group(3).strip()
    if raw.endswith(","):
        raw = raw[:-1].rstrip()
    if raw.startswith('"') and raw.endswith('"'):
        try:
            raw = str(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            raw = raw.strip('"')
    path = Path(where) if Path(where).is_absolute() else built / where
    return path, line, raw


def _enclosing_symbol(
    symbols: list[dict[str, object]], line: int
) -> dict[str, object] | None:
    enclosing = [
        symbol for symbol in symbols
        if int(symbol["line"]) <= line <= int(symbol["end_line"])
    ]
    return min(enclosing, key=lambda row: int(row["end_line"]) - int(row["line"])) \
        if enclosing else None


def _is_test_path(path: str) -> bool:
    parts = Path(path).parts
    return "tests" in parts or Path(path).name.startswith("test_")


def _changed_symbols(
    built: Path,
    index: dict[str, list[dict[str, object]]],
    before: dict[str, object] | None,
    changed_files: list[str],
) -> list[tuple[str, str, dict[str, object]]]:
    if not isinstance(before, dict):
        return []
    changed: list[tuple[str, str, dict[str, object]]] = []
    for named in changed_files:
        source = Path(named) if Path(named).is_absolute() else built / named
        label = _source_label(built, source)
        current = {str(row["qualname"]): row for row in index.get(label, [])}
        earlier = before.get(label)
        if not isinstance(earlier, dict):
            earlier = {}
        for qualname, row in current.items():
            old = earlier.get(qualname)
            if not isinstance(old, dict) or old.get("hash") != row.get("hash"):
                changed.append(("changed" if old else "added", label, row))
        for qualname, old in earlier.items():
            if qualname not in current and isinstance(old, dict):
                changed.append(("removed", label, {
                    "name": old.get("name") or qualname.rsplit(".", 1)[-1],
                    "qualname": qualname, "line": old.get("line") or 1,
                    "end_line": old.get("end_line") or old.get("line") or 1,
                    "calls": [], "hash": old.get("hash") or "",
                }))
    return changed


def _bounded_navigation(lines: list[str]) -> str:
    rendered: list[str] = []
    notice = "[navigation map clipped at its fixed character limit; inspect the source beyond it]"
    for line in lines:
        candidate = "\n".join(rendered + [line])
        if len(candidate) + len(notice) + 1 > NAVIGATION_CHAR_LIMIT:
            rendered.append(notice)
            break
        rendered.append(line)
    return "\n".join(rendered)


def _navigation_map(
    built: Path,
    item: dict[str, object],
    changed_files: list[str] | None = None,
    before: dict[str, object] | None = None,
) -> str:
    """Bounded structural starting points, generated without a builder or reader verdict."""

    index = _symbol_index(built)
    lines = [
        "Citation matches and their enclosing symbols (all matches up to the stated cap):"
    ]
    targets: set[str] = set()
    for part in item["parts"]:
        seen_at = part.get("seen_at")
        if not seen_at or not (citation := _citation(built, str(seen_at))):
            continue
        path, _old_line, text = citation
        label = _source_label(built, path)
        if not path.is_file():
            lines.append(f"- {part['part_id']}: {label} is no longer a file")
            continue
        wanted = " ".join(text.split()).lower()
        matches = [
            number for number, row in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            )
            if wanted and wanted in " ".join(row.split()).lower()
        ]
        shown = matches[:NAVIGATION_MATCH_LIMIT]
        if not shown:
            lines.append(f"- {part['part_id']}: no current match for {text!r} in {label}")
        for number in shown:
            enclosing = _enclosing_symbol(index.get(label, []), number)
            if enclosing:
                targets.add(str(enclosing["name"]))
                lines.append(
                    f"- {part['part_id']}: {label}:{number} inside "
                    f"{enclosing['qualname']} (lines {enclosing['line']}-{enclosing['end_line']})"
                )
            else:
                lines.append(f"- {part['part_id']}: {label}:{number} at module level")
        if len(matches) > len(shown):
            lines.append(
                f"- {part['part_id']}: {len(matches) - len(shown)} further matches exceed the "
                f"{NAVIGATION_MATCH_LIMIT}-match cap; search {label} before deciding"
            )

    if changed_files is not None:
        changed = _changed_symbols(built, index, before, changed_files)
        lines.append("Changed symbols, derived from the machinery's before-image:")
        if changed:
            for state, path, symbol in changed[:NAVIGATION_REFERENCE_LIMIT]:
                targets.add(str(symbol["name"]))
                lines.append(
                    f"- {state}: {path}:{symbol['line']} {symbol['qualname']}"
                )
            if len(changed) > NAVIGATION_REFERENCE_LIMIT:
                lines.append(
                    f"- {len(changed) - NAVIGATION_REFERENCE_LIMIT} further changed symbols "
                    "exceed the fixed reference cap; inspect the changed files"
                )
        else:
            lines.append("- none detected, or no before-image exists for this resumed item")

    references: list[tuple[str, int, str, str, dict[str, object]]] = []
    reference_keys: set[tuple[str, int, str, str]] = set()
    for path, symbols in index.items():
        for caller in symbols:
            for call in caller["calls"]:
                if str(call["name"]) in targets:
                    key = (
                        path, int(call["line"]), str(caller["qualname"]),
                        str(call["name"]),
                    )
                    if key not in reference_keys:
                        reference_keys.add(key)
                        references.append((*key, caller))
    source_refs = [row for row in references if not _is_test_path(row[0])]
    test_refs = [row for row in references if _is_test_path(row[0])]

    lines.append("Direct source consumers:")
    for path, number, caller, target, symbol in source_refs[:NAVIGATION_REFERENCE_LIMIT]:
        lines.append(f"- {path}:{number} inside {caller} calls {target}")
        later: list[tuple[str, int]] = []
        seen: set[str] = set()
        for call in reversed(symbol["calls"]):
            name, call_line = str(call["name"]), int(call["line"])
            if call_line > number and name not in seen and name != target:
                later.append((name, call_line))
                seen.add(name)
            if len(later) == 8:
                break
        if later:
            lines.append(
                "  later calls in this same consumer (mechanical order, not a finality claim): "
                + ", ".join(f"{name}@{call_line}" for name, call_line in reversed(later))
            )
    if len(source_refs) > NAVIGATION_REFERENCE_LIMIT:
        lines.append(
            f"- {len(source_refs) - NAVIGATION_REFERENCE_LIMIT} further source references "
            "exceed the fixed cap"
        )

    lines.append("Focused tests that call those symbols:")
    for path, number, caller, target, _symbol in test_refs[:NAVIGATION_REFERENCE_LIMIT]:
        lines.append(f"- {path}:{number} inside {caller} calls {target}")
    if not test_refs:
        lines.append("- none found by direct call name")
    if len(test_refs) > NAVIGATION_REFERENCE_LIMIT:
        lines.append(
            f"- {len(test_refs) - NAVIGATION_REFERENCE_LIMIT} further test references exceed "
            "the fixed cap"
        )
    return _bounded_navigation(lines)


def _reproduction_handoff(tests: str, navigation: str) -> str:
    """Turn mechanically found direct tests into a runnable, non-verdict handoff."""

    focused: list[str] = []
    for row in navigation.splitlines():
        match = re.match(r"^- (.+?):\d+ inside .+ calls .+$", row)
        if not match or not _is_test_path(match.group(1)):
            continue
        path = match.group(1)
        if path not in focused:
            focused.append(path)
    command = tests
    if focused:
        command += " " + " ".join(shlex.quote(path) for path in focused)
        scope = "direct focused tests found in the producer-to-consumer path manifest"
    else:
        scope = "the full supplied test command because no direct focused test was found"
    return (
        "\n\nRunnable real-path reproduction (mechanically derived):\n\n"
        f"    {command}\n\n"
        f"This runs {scope} through the repository's test entry point and real production path. "
        "It is a navigation aid, not acceptance evidence: inspect the behavior independently, "
        "and the machinery still decides only from verified citations and its final test gate."
    )


def _reader_context(
    built: Path, item: dict[str, object], changed_files: list[str],
    before: dict[str, object] | None = None, tests: str | None = None,
) -> str:
    """Neutral navigation for a blind reader: current locations and definitions, never a verdict."""

    places = [
        f"- {part['part_id']}: {_still_at(built, str(part['seen_at']))}"
        for part in item["parts"] if part.get("seen_at")
    ]
    drawn = _navigation_map(built, item, changed_files, before)
    mapped = f"\n\nStructural navigation map:\n{drawn}" if drawn else ""
    reproduction = _reproduction_handoff(tests, drawn) if tests else ""
    return READER_START.format(
        places="\n".join(places) or "- none", map=mapped + reproduction,
    )


def _records_in(directory: Path) -> list[tuple[Path, object]]:
    records = []
    for path in _readable(directory):
        records.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return records


def _reader_citation_errors(built: Path, directory: Path) -> list[str]:
    """Resolve every citation supporting a yes against the repository being accepted."""

    errors: list[str] = []
    root = built.resolve()
    for record_path, record in _records_in(directory):
        if not isinstance(record, dict) or record.get("answer") != "yes":
            continue
        citations = record.get("citations")
        if not isinstance(citations, list):
            continue
        for index, citation in enumerate(citations, start=1):
            label = f"{record_path.name}: citation {index}"
            if not isinstance(citation, dict):
                errors.append(f"{label} must be an object")
                continue
            where = citation.get("where")
            line = citation.get("line")
            text = citation.get("text")
            if not isinstance(where, str) or not where.strip():
                errors.append(f"{label} where must name a file inside built repository")
                continue
            source = Path(where)
            source = (source if source.is_absolute() else root / source).resolve()
            try:
                source.relative_to(root)
            except ValueError:
                errors.append(f"{label} points outside built repository: {where}")
                continue
            if not source.is_file():
                errors.append(f"{label} file does not exist: {where}")
                continue
            if not isinstance(line, int) or isinstance(line, bool) or line < 1:
                errors.append(f"{label} line must be a positive integer, got {line!r}")
                continue
            if not isinstance(text, str):
                errors.append(f"{label} text must be a string, got {type(text).__name__}")
                continue
            rows = source.read_text(encoding="utf-8").splitlines()
            if line > len(rows):
                errors.append(
                    f"{label} line {line} does not exist in {where}; file has {len(rows)} lines"
                )
                continue
            if rows[line - 1] != text:
                errors.append(
                    f"{label} text does not exactly match {where}:{line}; "
                    f"repository has {rows[line - 1]!r}, citation has {text!r}"
                )
    return errors


def _reader_record_errors(
    directory: Path, wanted: set[str], built: Path | None = None,
) -> list[str]:
    """Structural delivery errors only; substantive yes/no remains the blind reader's judgement."""

    errors: list[str] = []
    records = _records_in(directory)
    if len(records) != len(wanted):
        errors.append(f"expected {len(wanted)} record(s), found {len(records)}")
    names: list[str] = []
    for path, record in records:
        if not isinstance(record, dict):
            errors.append(f"{path.name}: record must be an object")
            continue
        part_id = record.get("part_id")
        if not isinstance(part_id, str):
            errors.append(f"{path.name}: part_id must be a string")
        else:
            names.append(part_id)
            if part_id not in wanted:
                errors.append(
                    f"{path.name}: part_id {part_id!r} is not one of {sorted(wanted)!r}"
                )
        if record.get("answer") not in {"yes", "no"}:
            errors.append(f"{path.name}: answer must be exactly 'yes' or 'no'")
        citations = record.get("citations")
        if not isinstance(citations, list):
            errors.append(f"{path.name}: citations must be a list")
        elif record.get("answer") == "yes" and not citations:
            errors.append(f"{path.name}: a yes answer needs at least one citation")
        if not isinstance(record.get("looked_at"), str) or not record.get("looked_at", "").strip():
            errors.append(f"{path.name}: looked_at must be a non-empty string")
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append(f"duplicate part ids: {duplicates!r}")
    missing = sorted(wanted - set(names))
    if missing:
        errors.append(f"missing part ids: {missing!r}")
    if built is not None:
        errors.extend(_reader_citation_errors(built, directory))
    return errors


def _test_removal_decision(
    ruling: object, disappeared: list[str],
) -> tuple[list[str], list[str]]:
    """Separate exact, owner-documented test removals from removals still needing a ruling."""

    removals = ruling.get("test_removals") if isinstance(ruling, dict) else None
    removals = removals if isinstance(removals, dict) else {}
    approved: list[str] = []
    for test in disappeared:
        row = removals.get(test)
        if not isinstance(row, dict) or row.get("authorized") is not True:
            continue
        owner_ruling = row.get("owner_ruling")
        coverage = row.get("replacement_or_remaining_coverage")
        if (isinstance(owner_ruling, str) and owner_ruling.strip()
                and isinstance(coverage, str) and coverage.strip()):
            approved.append(test)
    return approved, sorted(set(disappeared) - set(approved))


def _ruling_text(ruling: object) -> str:
    """Keep legacy string rulings and render structured owner decisions without inventing prose."""

    if isinstance(ruling, str):
        return ruling.strip()
    if not isinstance(ruling, dict):
        return ""
    lines = []
    general = ruling.get("owner_ruling")
    if isinstance(general, str) and general.strip():
        lines.append(general.strip())
    removals = ruling.get("test_removals")
    if isinstance(removals, dict):
        for test, row in removals.items():
            if not isinstance(row, dict) or row.get("authorized") is not True:
                continue
            owner = row.get("owner_ruling")
            coverage = row.get("replacement_or_remaining_coverage")
            if (isinstance(owner, str) and owner.strip()
                    and isinstance(coverage, str) and coverage.strip()):
                lines.append(f"Remove {test}: {owner.strip()} Coverage: {coverage.strip()}")
    return "\n".join(lines)


def _semantic_ruling_text(ruling: object) -> str:
    """The general meaning decision, excluding exact test-removal authorizations."""

    if isinstance(ruling, str):
        return ruling.strip()
    if not isinstance(ruling, dict):
        return ""
    owner_ruling = ruling.get("owner_ruling")
    return owner_ruling.strip() if isinstance(owner_ruling, str) else ""


def _ruling_sha256(ruling: object) -> str:
    """Identify the exact semantic owner words that an attempt was allowed to rely on."""

    text = _semantic_ruling_text(ruling)
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def _terminal_resume_authorized(ruling: object) -> bool:
    """A terminal item reopens only when the owner explicitly authorized that consequence."""

    return (
        isinstance(ruling, dict)
        and ruling.get("resume_after_terminal") is True
        and bool(_semantic_ruling_text(ruling))
    )


def _activate_ruling_epoch(
    work: Path, out: Path, rid: str, ruling: object, refusal_start: int,
) -> dict[str, object]:
    """Preserve stale active work and bind all later attempts to one exact ruling revision."""

    history_number = 1
    while (out / f"ruling-history-{history_number}").exists():
        history_number += 1
    history = out / f"ruling-history-{history_number}"
    pending = [
        out / "change.json",
        out / "navigation-before.json",
        out / "tests-before.json",
        out / "tests-after.json",
        work / f"build-{rid}-scratch",
    ]
    for index in range(1, PASSES + 1):
        pending.extend([
            work / f"check-{rid}-{index}",
            work / f"check-{rid}-{index}-scratch",
        ])
    # Attempt numbering restarts inside a new ruling window, so an observation left under the old
    # window's attempt number would be read as this attempt's. It travels into history with the
    # rest of the stale work instead.
    pending.extend(sorted(out.glob("files-observed-*.json")))
    moved = []
    for path in pending:
        if not path.exists():
            continue
        history.mkdir(parents=True, exist_ok=True)
        destination = history / path.name
        path.rename(destination)
        moved.append(path.name)
    if moved:
        (history / "manifest.json").write_text(json.dumps({
            "reason": "owner ruling changed after earlier work",
            "preserved": moved,
            "refusals_before_ruling": refusal_start,
        }, indent=2), encoding="utf-8")
    state = {
        "ruling_sha256": _ruling_sha256(ruling),
        "refusal_start": refusal_start,
        "history": history.name if moved else None,
        "baseline_refreshed": True,
    }
    (out / "ruling-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def _touched(built: Path) -> set[str]:
    """Which files of the built system differ from what was committed, right now.

    Observed, not reported. An agent that says what it is doing is making a claim; the repository
    saying which files have changed under it is the system watching the work happen. It costs
    under a tenth of a second, which is why it can be asked every thirty seconds.
    """

    done = subprocess.run(["git", "diff", "--name-only"], cwd=str(built),
                          capture_output=True, text=True, check=False)
    return {line.strip() for line in done.stdout.splitlines() if line.strip()}


def _still_at(built: Path, seen_at: str) -> str:
    """Point the citation at where its text is now, before a builder is sent to the old line.

    A citation is a file, a line and that line's text, recorded when the readers judged the
    sentence not yet true. Every build since has moved lines in that file. The first builder handed
    one spent its time discovering that: the line it was sent to no longer held the quoted text,
    which had moved a thousand lines down. Code can settle that before anybody is asked — the text
    is either still in the file or it is not, and finding it is a search, not a judgement.

    A quote that occurs exactly once is that line wherever it moved to. Occurring several times, or
    not at all, the line number is dropped rather than guessed: a wrong number sends the builder
    somewhere confidently useless, and no number sends it looking, which is at least honest.
    """

    match = re.match(r"^(.*?):(\d+) — (.*)$", seen_at, re.S)
    if not match:
        return seen_at
    where, line, text = match.group(1), int(match.group(2)), match.group(3).strip().strip('"')
    path = Path(where) if Path(where).is_absolute() else built / where
    if not path.is_file():
        return f"{where} — no longer a file; find where this is decided: {text}"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    wanted = " ".join(text.split()).lower()
    if 1 <= line <= len(lines) and wanted in " ".join(lines[line - 1].split()).lower():
        return seen_at
    found = [n for n, row in enumerate(lines, start=1) if wanted in " ".join(row.split()).lower()]
    if len(found) == 1:
        return f"{where}:{found[0]} — {text}   (it has moved since it was read; this is where it is now)"
    return (f"{where} — the quoted text is no longer at line {line} and "
            f"{'appears in several places' if found else 'is not in the file'}; "
            f"find where this is decided: {text}")


def say(work: Path, what: str, **facts: object) -> None:
    """Write one line to the feed, now, so somebody can watch this run while it is running.

    Everything this step recorded before was a finished artefact: a change, a verdict, a done
    record. Between them it was silent for eight or nine minutes at a stretch, and the only way to
    tell working from stuck was to compare file timestamps afterwards and guess. A run that cannot
    say what it is doing cannot be supervised, and on 2026-08-10 one item spent ninety minutes
    failing the same way four times with nobody able to see it.

    One line per thing that starts or finishes, appended and flushed immediately — not buffered,
    not held until the stage ends, not written at the end of the run. `tail -f` on this file is the
    whole interface.
    """

    line = {"at": time.strftime("%H:%M:%S"), "what": what, **facts}
    with (work / "feed.jsonl").open("a", encoding="utf-8") as feed:
        feed.write(json.dumps(line, default=str) + "\n")
        feed.flush()


def _timed(work: Path, what: str, **facts: object):
    """Say a thing started, and say what it cost when it ends, whatever way it ends."""

    class Span:
        def __enter__(self):
            self.began = time.monotonic()
            say(work, what + " started", **facts)
            return self

        def __exit__(self, kind, value, trace):
            say(work, what + (" failed" if kind else " finished"),
                seconds=round(time.monotonic() - self.began, 1),
                **({"because": str(value)[:200]} if kind else {}), **facts)
            return False

    return Span()


def drive(order: dict[str, object], work: Path, built: Path, tests: str,
          *, with_body: bool = False, prepare_universal_paths: bool = False,
          reader_map: bool = False, repair_reader_records: bool = False,
          owner_approved: bool = False) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    _bootstrap_controller_state(order, work, tests)
    item = next_item(order, work)
    if item is None:
        say(work, "the order is finished")
        return {"finished": "every item in the order has been built and verified"}

    # A ruling is the owner's answer to something only they can settle. It is optional, it is
    # quoted to the builder rather than summarised, and it lives on disk so the next run says the
    # same thing this one did.
    rulings_path = work / "rulings.json"
    rulings = (json.loads(rulings_path.read_text(encoding="utf-8"))
               if rulings_path.exists() else {})

    rid = str(item["requirement_id"])
    out = work / f"build-{rid}"
    out.mkdir(parents=True, exist_ok=True)
    ruling = rulings.get(rid)
    ruling_text = _ruling_text(ruling)
    ruling_sha256 = _ruling_sha256(ruling)
    all_refused = _controller_refused_paths(work, rid, out)
    state_path = out / "ruling-state.json"
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.is_file() else None
    )
    refusal_start = 0
    if isinstance(state, dict):
        refusal_start = int(state.get("refusal_start", 0))
        prior_epoch_refusals = all_refused[refusal_start:]
        if state.get("ruling_sha256") != ruling_sha256:
            if ruling_sha256 and (
                len(prior_epoch_refusals) < ATTEMPTS
                or _terminal_resume_authorized(ruling)
            ):
                state = _activate_ruling_epoch(
                    work, out, rid, ruling, len(all_refused),
                )
                refusal_start = len(all_refused)
            elif prior_epoch_refusals:
                terminal_path = prior_epoch_refusals[-1]
                terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
                terminal["for_a_person"] = (
                    "The owner ruling changed after this attempt stopped. Authorize "
                    "resume_after_terminal for the new ruling before another builder starts."
                )
                say(work, "terminal refusal read", item=rid,
                    attempts=len(prior_epoch_refusals))
                return terminal
        if not state.get("baseline_refreshed"):
            tests_before = out / "tests-before.json"
            if tests_before.is_file():
                history_name = state.get("history")
                history = (
                    out / str(history_name)
                    if history_name else out / "ruling-history-baseline"
                )
                history.mkdir(parents=True, exist_ok=True)
                destination = history / "tests-before.json"
                suffix = 1
                while destination.exists():
                    destination = history / f"tests-before-{suffix}.json"
                    suffix += 1
                tests_before.rename(destination)
            state["baseline_refreshed"] = True
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    elif ruling_sha256:
        if len(all_refused) < ATTEMPTS or _terminal_resume_authorized(ruling):
            state = _activate_ruling_epoch(work, out, rid, ruling, len(all_refused))
            refusal_start = len(all_refused)

    refused = all_refused[refusal_start:]
    if len(refused) >= ATTEMPTS:
        terminal_path = refused[-1]
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        terminal_handoff_was_missing = "for_a_person" not in terminal
        terminal.setdefault(
            "for_a_person",
            f"{len(refused)} attempts under the current owner ruling have been refused. "
            "What is being asked may not be buildable as stated, or the sentences may be "
            "describing something the system does elsewhere.",
        )
        if terminal_handoff_was_missing:
            terminal_path.write_text(json.dumps(terminal, indent=2), encoding="utf-8")
        say(work, "terminal refusal read", item=rid, attempts=len(refused))
        return terminal
    parts = "\n".join(f"- {p['part']}" for p in item["parts"])
    named_parts = "\n".join(f"- [{p['part_id']}] {p['part']}" for p in item["parts"])

    say(work, "item taken up", item=rid, parts=len(item["parts"]),
        attempt=len(refused) + 1)

    # 1 · what passes now, recorded before anything is touched.
    before_path = out / "tests-before.json"
    before = _read_controller_test_record(work, rid, before_path, tests)
    if before is None:
        quiet = _repository_state(built, work)
        if quiet is not None:
            _write_controller_record(work, rid, out / "files-before-tests.json", quiet)
        with _timed(work, "tests before the change", item=rid):
            before = _failures(built, tests)
        _write_controller_record(work, rid, before_path, before)
        # The baseline run touched nothing anybody asked for, so whatever moved is what running
        # the tests writes. Recorded now, it is subtracted from what the builder moved later.
        if quiet is not None:
            after_quiet = _repository_state(built, work)
            if after_quiet is not None:
                _write_controller_record(
                    work, rid, out / "files-the-tests-write.json",
                    _what_running_the_tests_writes(quiet, after_quiet),
                )
    say(work, "tests before the change read", item=rid, already_failing=len(before["failed"]))

    approved_baseline_removals, _ = _test_removal_decision(
        rulings.get(rid), list(before.get("names") or []),
    )
    protected_identities = sorted(
        set(before.get("names") or []) - set(approved_baseline_removals)
    )
    protected_path = out / "protected-test-identities.json"
    protected_path.write_text(
        json.dumps(
            {"count": len(protected_identities), "identities": protected_identities},
            indent=2,
        ),
        encoding="utf-8",
    )

    # 2 · the change. A refused attempt is moved aside so the builder is asked again, carrying what
    # the readers objected to. Without this the step returned 'not built' and handed back nothing,
    # and the whole order stalled on the first honest refusal.
    change_path = out / "change.json"
    navigation_before_path = out / "navigation-before.json"
    files_before_path = out / "files-before.json"
    if not change_path.exists():
        if not navigation_before_path.exists():
            navigation_before_path.write_text(
                json.dumps(_symbol_snapshot(built), indent=2), encoding="utf-8"
            )
        if _read_controller_record(work, rid, files_before_path) is None:
            state = _repository_state(built, work)
            if state is not None:
                _write_controller_record(work, rid, files_before_path, state)
        instruction = BUILD.format(
            built=built, requirement=item["requirement"], parts=parts, out=out,
        )
        instruction += PROTECTED_TEST_IDENTITIES.format(
            count=len(protected_identities), path=protected_path,
        )
        # Where the readers who put this item on the list said they looked. They cited a file and
        # a line for every part; the order carried none of it, so each builder searched a
        # five-thousand-line file again for a place already written down.
        seen_at = "\n".join(
            f"- {p['part_id']}: {_still_at(built, str(p['seen_at']))}"
            for p in item["parts"] if p.get("seen_at")
        )
        if seen_at:
            instruction += SEEN_AT.format(seen_at=seen_at)
        drawn = _navigation_map(built, item)
        if drawn:
            instruction += MAP.format(map=drawn)
            instruction += _reproduction_handoff(tests, drawn)
        if with_body:
            bodies = "\n\n".join(dict.fromkeys(
                found for p in item["parts"] if p.get("seen_at")
                for found in [_body_at(built, str(p["seen_at"]))] if found
            ))
            if bodies:
                instruction += BODY.format(bodies=bodies)
        if prepare_universal_paths:
            instruction += _universal_preparation(str(item["requirement"]))
        if ruling_text:
            instruction += RULED.format(ruling=ruling_text)
        if all_refused:
            last = json.loads(all_refused[-1].read_text(encoding="utf-8"))
            instruction += AGAIN.format(
                what_changed=last["what_changed"],
                objections="\n".join(f"- {line}" for line in last["objections"]),
            )
        say(work, "handing the change out", item=rid, attempt=len(refused) + 1,
            told_where=sum(1 for p in item["parts"] if p.get("seen_at")),
            of_parts=len(item["parts"]), instruction_characters=len(instruction))
        return {
            "stopped": "building" if not refused else "building again",
            "item": rid,
            "requirement": item["requirement"],
            "attempt": len(refused) + 1,
            "refusal_number": len(all_refused) + 1,
            "already_failing_before_the_change": len(before["failed"]),
            "work": [_packet(
                instruction, out, out.parent / f"build-{rid}-scratch", blind=False,
                built=built, tests=tests,
                wants="change.json", owner_approved=owner_approved,
            )],
        }
    change = _reconcile_with_the_repository(
        work, rid, out, built, change_path, len(refused) + 1,
    )

    # A builder that changed nothing has produced nothing to check. Sending two readers at the
    # unchanged system to ask whether the sentence is true now is work whose answer is already
    # known — it was 'no' when the item went on the list and nothing has moved since. On the run
    # that made this necessary, a builder said plainly that the change it would have to make
    # contradicts an existing test, and the step sent two readers anyway: six minutes of reading
    # to rediscover the builder's own first sentence, and then a refusal that spent an attempt.
    # A builder stopping because a test contradicts the requirement is the owner's to settle, and
    # the step says so instead of asking again.
    if not change.get("files"):
        # It is a refusal, and it takes the refusal path: set aside, asked again carrying its own
        # words, and after the attempts are spent it goes to the owner. What it must not do is go
        # to the readers — there is nothing to read, the answer was 'no' when the item went on the
        # list and nothing has moved since, and the round would cost two agents to be told what
        # this record already says in its first sentence.
        attempt = len(refused) + 1
        refusal_number = len(all_refused) + 1
        kept = out / f"refused-{refusal_number}.json"
        receipt = {
            "item": rid, "requirement": item["requirement"], "attempt": attempt,
            "refusal_number": refusal_number, "ruling_sha256": ruling_sha256,
            "what_changed": change.get("what_changed"), "left_alone": change.get("left_alone"),
            "objections": ["the builder changed nothing: "
                           + str(change.get("what_changed") or "")[:600]],
            "built": False,
        }
        if attempt >= ATTEMPTS:
            receipt["for_a_person"] = (
                "Only the owner can settle this. Put their answer in rulings.json under this item."
            )
        _write_controller_record(work, rid, kept, receipt)
        change_path.unlink()
        say(work, "builder changed nothing", item=rid, attempt=attempt,
            because=str(change.get("what_changed"))[:200])
        if attempt >= ATTEMPTS:
            return {**receipt,
                "stopped": "the builder changed nothing, every attempt", "item": rid,
                "requirement": item["requirement"], "attempts": attempt,
                "the_builder_says": change.get("what_changed"),
                "work": [],
            }
        return drive(
            order, work, built, tests, with_body=with_body,
            prepare_universal_paths=prepare_universal_paths, reader_map=reader_map,
            repair_reader_records=repair_reader_records, owner_approved=owner_approved,
        )

    # A missing pre-existing test identity is a mechanical fact, not a question for two semantic
    # readers.  Catch it before buying their work and return every exact identity to the builder.
    # The final gate remains authoritative and repeats the comparison after the readers finish.
    readers_have_started = any(
        (work / f"check-{rid}-{index}").is_dir()
        for index in range(1, PASSES + 1)
    )
    collection = (
        _test_inventory(built, tests)
        if not readers_have_started else {"exit_code": None, "names": []}
    )
    if collection["exit_code"] == 0:
        gone_before_reading = sorted(
            set(before.get("names") or []) - set(collection.get("names") or [])
        )
        approved_removals, removals_needing_owner = _test_removal_decision(
            rulings.get(rid), gone_before_reading,
        )
        if removals_needing_owner:
            objections = [
                f"{test} disappeared before either blind reader; restore that exact collected "
                "identity and make it exercise the required behavior, or obtain an exact owner "
                "ruling authorizing its removal"
                for test in removals_needing_owner
            ]
            attempt = len(refused) + 1
            refusal_number = len(all_refused) + 1
            verdict = {
                "item": rid,
                "requirement": item["requirement"],
                "changed": change["files"],
                "builder_said_changed": change.get("builder_said_changed"),
                "changed_without_saying_so": change.get("changed_without_saying_so"),
                "what_changed": change.get("what_changed"),
                "left_alone": change.get("left_alone"),
                "test_command_exit_code": None,
                "tests_that_broke": [],
                "tests_that_stopped_existing": gone_before_reading,
                "approved_test_removals": approved_removals,
                "test_removals_needing_owner": removals_needing_owner,
                "removals_the_builder_declared": [
                    str(row.get("test")) for row in (change.get("tests_changed") or [])
                    if isinstance(row, dict)
                ],
                "parts_both_readers_call_true": [],
                "parts_not_agreed": [],
                "parts_no_reader_answered": [
                    str(part["part_id"]) for part in item["parts"]
                ],
                "answers_under_a_name_no_part_has": [],
                "reader_citation_errors": [],
                "built": False,
                "attempt": attempt,
                "refusal_number": refusal_number,
                "ruling_sha256": ruling_sha256,
                "objections": objections,
            }
            if attempt >= ATTEMPTS:
                verdict["for_a_person"] = (
                    f"{attempt} attempts removed a protected test identity before reading. "
                    "Only the owner can authorize its removal."
                )
            _write_controller_record(
                work, rid, out / f"refused-{refusal_number}.json", verdict,
            )
            change_path.rename(out / f"change-{refusal_number}.json")
            say(work, "test identities missing before readers", item=rid,
                identities=removals_needing_owner, attempt=attempt)
            return {
                **verdict,
                "stopped": "correcting protected test identities before reading",
            }

    # 3 · the same question, asked again, by two readers who cannot see each other.
    before_navigation = None
    if reader_map and navigation_before_path.is_file():
        try:
            before_navigation = json.loads(
                navigation_before_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError, ValueError):
            before_navigation = None
    reader_context = _reader_context(
        built, item, [str(path) for path in change["files"]], before_navigation, tests,
    )
    semantic_ruling_text = _semantic_ruling_text(ruling)
    ruling_context = (
        RULING_FOR_READER.format(ruling=semantic_ruling_text)
        if semantic_ruling_text else ""
    )
    waiting = []
    for index in range(1, PASSES + 1):
        checked = work / f"check-{rid}-{index}"
        answers = _answers_in(checked)
        if answers == 0 or (not repair_reader_records and answers < len(item["parts"])):
            waiting.append(_packet(
                VERIFY.format(built=built, named_parts=named_parts, out=checked)
                + ruling_context
                + reader_context,
                checked, work / f"check-{rid}-{index}-scratch", blind=True,
                built=built, tests=tests,
                expect=len(item["parts"]), owner_approved=owner_approved,
            ))
    if waiting:
        say(work, "change in hand, handing it to the checkers", item=rid,
            changed=change["files"], checkers=len(waiting))
        return {"stopped": "checking the change", "item": rid, "changed": change["files"],
                "work": waiting}

    # A malformed delivery says nothing about whether the change is right. Repair only the seat
    # that broke the record contract, preserving the build and the other blind reader's answer.
    # A second malformed delivery stops for a person instead of silently consuming a build attempt.
    if repair_reader_records:
        wanted = {str(part["part_id"]) for part in item["parts"]}
        repairs = []
        for index in range(1, PASSES + 1):
            checked = work / f"check-{rid}-{index}"
            errors = _reader_record_errors(checked, wanted, built)
            if not errors:
                continue
            earlier = sorted(work.glob(f"check-{rid}-{index}-invalid-*"))
            if len(earlier) >= RECORD_REPAIR_ATTEMPTS:
                say(work, "reader record repair exhausted", item=rid, checker=index,
                    errors=errors)
                return {
                    "stopped": "reader record repair needs a person", "item": rid,
                    "changed": change["files"], "checker": index, "errors": errors,
                    "work": [],
                }
            repair_number = len(earlier) + 1
            checked.rename(work / f"check-{rid}-{index}-invalid-{repair_number}")
            instruction = (
                VERIFY.format(built=built, named_parts=named_parts, out=checked)
                + ruling_context
                + reader_context
                + RECORD_REPAIR.format(errors="\n".join(f"- {error}" for error in errors))
            )
            repairs.append(_packet(
                instruction, checked,
                work / f"check-{rid}-{index}-repair-{repair_number}-scratch", blind=True,
                built=built, tests=tests,
                expect=len(item["parts"]), owner_approved=owner_approved,
            ))
        if repairs:
            say(work, "repairing reader records", item=rid, checkers=len(repairs))
            return {
                "stopped": "repairing reader records", "item": rid,
                "changed": change["files"], "work": repairs,
            }

    # 4 · the verdict. Nothing that passed before may fail now, and both readers must say yes.
    with _timed(work, "tests after the change", item=rid):
        after = _failures(built, tests)
    _write_controller_record(work, rid, out / "tests-after.json", after)
    broke = sorted(set(after["failed"]) - set(before["failed"]))
    # A test that no longer exists cannot fail, so the gate above cannot see it go. This is not a
    # judgement about whether the removal was right — it is the removal being written down.
    gone = sorted(set(before.get("names") or []) - set(after.get("names") or []))
    approved_removals, removals_needing_owner = _test_removal_decision(
        rulings.get(rid), gone,
    )

    # One answer per part per pass, and every one of them yes. Counting distinct answers instead
    # of answers-per-pass is how the first run of this step passed a part that only one reader had
    # answered: the two readers had named the same sentence differently, so each name carried a
    # single 'yes' and the set of answers looked unanimous.
    said: dict[str, list[str]] = {}
    for index in range(1, PASSES + 1):
        for _, record in _records_in(work / f"check-{rid}-{index}"):
            if not isinstance(record, dict):
                continue
            said.setdefault(str(record.get("part_id")), []).append(str(record.get("answer")))
    wanted = {str(p["part_id"]) for p in item["parts"]}
    unproven = sorted(pid for pid in wanted
                      if said.get(pid, []).count("yes") < PASSES)
    missing = sorted(pid for pid in wanted if pid not in said)
    unnamed = sorted(set(said) - wanted)
    citation_errors = [
        error
        for index in range(1, PASSES + 1)
        for error in _reader_citation_errors(built, work / f"check-{rid}-{index}")
    ]

    verdict = {
        "item": rid,
        "requirement": item["requirement"],
        "changed": change["files"],
        "builder_said_changed": change.get("builder_said_changed"),
        "changed_without_saying_so": change.get("changed_without_saying_so"),
        "what_changed": change.get("what_changed"),
        "left_alone": change.get("left_alone"),
        "test_command_exit_code": after["exit_code"],
        "tests_that_broke": broke,
        "tests_that_stopped_existing": gone,
        "approved_test_removals": approved_removals,
        "test_removals_needing_owner": removals_needing_owner,
        "removals_the_builder_declared": [
            str(row.get("test")) for row in (change.get("tests_changed") or [])
            if isinstance(row, dict)
        ],
        "parts_both_readers_call_true": sorted(wanted - set(unproven)),
        "parts_not_agreed": unproven,
        "parts_no_reader_answered": missing,
        "answers_under_a_name_no_part_has": unnamed,
        "reader_citation_errors": citation_errors,
        "built": (after["exit_code"] == 0 and not broke and not unproven
                  and not missing and not unnamed and not citation_errors
                  and not removals_needing_owner),
    }
    if verdict["built"]:
        _write_controller_record(work, rid, out / "done.json", verdict)
        return verdict

    # Refused. Keep everything — the change stays in place and the reading stays on disk — but
    # record why, set this attempt aside, and let the next run hand it back to a builder.
    objections = []
    for index in range(1, PASSES + 1):
        for _, record in _records_in(work / f"check-{rid}-{index}"):
            if not isinstance(record, dict):
                continue
            if str(record.get("answer")) != "yes":
                objections.append(
                    f"{record.get('part_id')}: {record.get('looked_at') or 'no reason given'}"
                )
    if broke:
        objections.append("these tests passed before the change and fail after it: "
                          + ", ".join(broke))
    if after["exit_code"] != 0:
        objections.append(f"test command exited {after['exit_code']}")
    objections.extend(citation_errors)
    objections.extend(
        f"{test} disappeared; authorize this exact removal in rulings.json with "
        "owner_ruling and replacement_or_remaining_coverage"
        for test in removals_needing_owner
    )

    attempt = len(refused) + 1
    refusal_number = len(all_refused) + 1
    verdict["attempt"] = attempt
    verdict["refusal_number"] = refusal_number
    verdict["ruling_sha256"] = ruling_sha256
    verdict["objections"] = objections
    if attempt >= ATTEMPTS:
        verdict["for_a_person"] = (
            f"{attempt} attempts have been refused. What is being asked may not be buildable as "
            "stated, or the sentences may be describing something the system does elsewhere."
        )
    _write_controller_record(
        work, rid, out / f"refused-{refusal_number}.json", verdict,
    )
    change_path.rename(out / f"change-{refusal_number}.json")
    for index in range(1, PASSES + 1):
        checked = work / f"check-{rid}-{index}"
        if checked.is_dir():
            checked.rename(work / f"check-{rid}-{index}-attempt-{refusal_number}")

    return verdict



def _launch(jobs: list[dict[str, object]], command: str, built: Path,
            work: Path, tag: str) -> list[dict[str, object]]:
    """Run the packets this step just wrote, instead of handing them to whoever is driving.

    Until now the step wrote the instruction and a person passed it to a reader. Nothing about
    that hand improved the answer — the gates decide the verdict and they do not know whose hand
    pressed start — but it set the pace: the loop moved as fast as somebody was watching it, and
    stopped when they stopped.

    What does not change is who reads. The command is supplied from outside, exactly as the reader
    was before; this machinery still never chooses one, and every reader still writes down what it
    is. The instruction goes in on standard input so nothing about it can be reshaped by a shell.
    """

    parts = validate_reader_command(command)
    started = []

    def run(number: int, job: dict[str, object]) -> dict[str, object]:
        # Wait for the work, not for the process. On the first long unattended run a builder wrote
        # its change and its own record and then stayed alive: nineteen minutes later the loop had
        # not moved, because it was waiting on a process that had already done everything asked of
        # it. What the next step reads is what is on disk, so that is what waiting means here.
        waiting_for = Path(str(job["waiting_for"]))
        scratch = Path(str(job.get("scratch") or work / f"launch-{tag}-{number}-scratch"))
        uv_cache = scratch / "uv-cache"
        uv_cache.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["UV_CACHE_DIR"] = str(uv_cache)
        # `uv run --with ...` initializes its dependency-sync HTTP client even with a warm cache.
        # In a managed macOS worker that calls SCDynamicStore, which is unavailable and makes uv
        # panic before pytest starts.  The built repository already owns the prepared environment;
        # no-sync keeps the prescribed command intact and uses that environment without network or
        # package mutation.  The outer machinery still runs the same test command before and after.
        environment["UV_NO_SYNC"] = "1"
        wanted = int(job.get("expect") or 1)
        pattern = str(job.get("wants") or "*.json")
        started = subprocess.Popen(
            parts, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(built), text=True, env=environment,
        )
        started.stdin.write(str(job["instruction"]))
        started.stdin.close()

        # A controller restart begins its round numbers again.  The earlier name contained only
        # that round and reader seat, so a restart overwrote the very failed launch needed to
        # diagnose why it restarted.  The delivery identity and OS pid make each launch record
        # collision-proof without changing any worker or acceptance behavior.
        identity = re.sub(r"[^A-Za-z0-9_.-]+", "-", waiting_for.name).strip("-") or "work"
        log = work / f"launch-{tag}-{number}-{identity}-{started.pid}.log"

        began = time.monotonic()
        untouched = _touched(built)
        say(work, "agent started", job=f"{tag}-{number}", waiting_for=waiting_for.name,
            wants=wanted, pid=started.pid)

        # What the agent is actually doing, as it does it. The first version of this feed said
        # only "still working, nothing written" every thirty seconds — a heartbeat, which tells
        # you a process is alive and nothing about whether it is doing the right thing. It cost a
        # line every half minute and carried no information. When the reader command streams its
        # events, each tool it uses is named here instead: which file it read, what it searched
        # for, what it ran. When it does not stream, this stays silent rather than inventing a
        # heartbeat.
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        failures: list[str] = []
        watching = threading.Thread(
            target=_watch,
            args=(started.stdout, work, f"{tag}-{number}", stdout_lines, failures),
            daemon=True,
        )
        draining_stderr = threading.Thread(
            target=_drain, args=(started.stderr, stderr_lines), daemon=True,
        )
        watching.start()
        draining_stderr.start()

        delivered = False
        while started.poll() is None:
            if _delivered(waiting_for, pattern) >= wanted:
                # It has delivered. Give it a short grace to close itself, then stop waiting.
                for _ in range(GRACE_SECONDS):
                    if started.poll() is not None:
                        break
                    time.sleep(1)
                if started.poll() is None:
                    started.terminate()
                    delivered = True
                break
            time.sleep(2)

        started.wait()
        watching.join()
        draining_stderr.join()
        out = "".join(stdout_lines)
        err = "".join(stderr_lines)
        log.write_text(out + ("\n--- stderr ---\n" + err if err else "")
                       + ("\n--- it had already written its answer and was still running; "
                          "the step stopped waiting\n" if delivered else ""), encoding="utf-8")
        wrote = _delivered(waiting_for, pattern)
        say(work, "agent finished", job=f"{tag}-{number}", wrote=wrote, of=wanted,
            minutes=round((time.monotonic() - began) / 60, 1),
            exit_code=started.returncode, stopped_after_delivering=delivered,
            failure=failures[-1] if failures else None, log=log.name)
        return {"exit_code": started.returncode, "log": str(log),
                "stopped_after_delivering": delivered, "wrote": wrote,
                "failure": failures[-1] if failures else None}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(run, number, job) for number, job in enumerate(jobs, start=1)]
        for future in futures:
            started.append(future.result())
    return started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", type=Path, default=None,
                        help="the build order. Omit it and give --report instead: the ordering is "
                             "then done here, once, and the order written into --work.")
    parser.add_argument("--report", type=Path, default=None,
                        help="the requirements machine's report. Given this, the order is derived "
                             "before building, so starting the whole thing is one command.")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--built", type=Path, required=True)
    parser.add_argument("--tests", required=True,
                        help="the built system's own test command, run from its root")
    parser.add_argument("--reader-command", default=None,
                        help="a command that takes an instruction on standard input and carries "
                             "it out. Given one, the step runs its own builders and readers "
                             "instead of handing the packets back. It never picks the reader: "
                             "whoever runs this supplies the command, and the reader still says "
                             "in its own record what it is. Start it plainly — no personal rules, "
                             "memory or hooks: a worker given one sentence spent its first minute "
                             "loading an operator's whole working agreement and read it four times "
                             "over one job. Have it stream what it does, or this step's feed can "
                             "only say that it is breathing.")
    parser.add_argument("--with-body", action="store_true",
                        help="an experiment: hand the builder the lines each cited place sits in")
    parser.add_argument(
        "--prepare-universal-paths", action="store_true",
        help="an experiment: ask builders of universal claims to prepare every reached path",
    )
    parser.add_argument(
        "--reader-map", action="store_true",
        help="retained compatibility flag; the bounded producer-to-consumer path manifest is "
             "now always supplied to builders and blind readers",
    )
    parser.add_argument(
        "--repair-reader-records", action="store_true",
        help="repair one malformed reader delivery in place instead of rebuilding the item",
    )
    parser.add_argument(
        "--owner-approved", action="store_true",
        help="relay that the owner approved the bounded item edits and verification; never set "
             "this flag without their explicit approval",
    )
    parser.add_argument(
        "--recover-clean-baseline",
        metavar="ITEM",
        help="recover one worker-corrupted clean baseline from the controller feed, neutral "
             "pre-builder test-symbol snapshot, and a fresh clean full-suite result",
    )
    parser.add_argument("--items", type=int, default=1,
                        help="how many items may be taken without a person looking. The loop stops "
                             "at this many, or sooner on anything a person has to answer.")
    args = parser.parse_args(argv)
    work, built = args.work.resolve(), args.built.resolve()

    # Ordering and building were two commands because they were built as two. Nothing needs them
    # to be: the ordering is done once per list and skips itself afterwards, so it can simply
    # happen first. Kept as a separate step only for the case where somebody already has an order.
    if args.order is None:
        if args.report is None:
            parser.error("give either --order or --report")
        import run  # noqa: PLC0415 — imported here because run.py imports this module
        if args.reader_command:
            ordering = run.complete_ordering(
                args.report.resolve(), work, 550, 0.15, args.reader_command, built,
            )
        else:
            ordering = run.drive(args.report.resolve(), work, 550, 0.15)
            if ordering.get("work"):
                return _say({"stopped": "reading the pairs, and no reader command was given",
                             "work": ordering["work"]})
        if not ordering.get("order"):
            return _say(ordering)
        args.order = Path(ordering["order"])

    order = json.loads(args.order.read_text(encoding="utf-8"))

    if args.recover_clean_baseline:
        if not args.owner_approved:
            parser.error("--recover-clean-baseline requires --owner-approved")
        print(json.dumps(recover_clean_baseline(
            order, work, built, args.tests, args.recover_clean_baseline,
        ), indent=2))
        return 0

    if not args.reader_command:
        print(json.dumps(drive(
            order, work, built, args.tests, with_body=args.with_body,
            prepare_universal_paths=args.prepare_universal_paths,
            reader_map=args.reader_map, repair_reader_records=args.repair_reader_records,
            owner_approved=args.owner_approved,
        ), indent=2))
        return 0

    # The brake. An unattended loop with no cap is the one way this can do harm at a speed nobody
    # sees, so it stops at --items, and it stops the moment a round of reading leaves the step
    # exactly where it was — a reader that wrote nothing would otherwise be asked forever.
    settled, rounds, stuck, seen = [], 0, 0, None
    while True:
        result = drive(
            order, work, built, args.tests, with_body=args.with_body,
            prepare_universal_paths=args.prepare_universal_paths,
            reader_map=args.reader_map, repair_reader_records=args.repair_reader_records,
            owner_approved=args.owner_approved,
        )
        if "built" in result:
            settled.append({"item": result.get("item"), "built": result.get("built")})
            say(work, "verdict", item=result.get("item"), built=result.get("built"),
                done_so_far=sum(1 for row in settled if row["built"]), of=args.items,
                why=result.get("why") or result.get("not_built"))
            if result.get("for_a_person"):
                return _say({"items": settled, "stopped_at": "the configured attempt limit",
                             "last": result})
            # The cap counts items finished, not verdicts reached. On the first unattended run
            # --items 10 stopped after six items, because four of the ten verdicts were refusals
            # of one item that then passed on its fourth attempt. A refusal is the retry path
            # working, not work delivered, and a cap that counts it stops the loop early and
            # reports a number nobody can compare with the order.
            if sum(1 for row in settled if row["built"]) >= args.items:
                return _say({"items": settled, "stopped_at": "the number of items asked for",
                             "last": result})
            continue
        jobs = result.get("work")
        if not jobs:
            return _say({"items": settled, "stopped_at": "the step handed back no work",
                         "last": result})
        here = (result.get("item"), result.get("stopped"), len(jobs))
        stuck = stuck + 1 if here == seen else 0
        seen = here
        if stuck >= 2:
            return _say({"items": settled, "stopped_at": "the reading changed nothing twice over",
                         "last": result})
        rounds += 1
        result["readers"] = _launch(jobs, args.reader_command, built, work, f"{rounds}")


def _say(result: dict[str, object]) -> int:
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
