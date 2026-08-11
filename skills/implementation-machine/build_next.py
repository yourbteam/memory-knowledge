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
import concurrent.futures
import json
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path

PASSES = 2

#: How many times one item may be handed back to a builder before it goes to a person. A refusal is
#: information, not failure — the first item refused here was refused rightly, and a machinery with
#: no second attempt would have stalled on it. But an item that cannot be made true in three tries
#: is telling us something the builder cannot fix by trying again.
ATTEMPTS = 3

#: How long a reader that has already written its answer is given to close itself.
GRACE_SECONDS = 20

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
    "\n\nWhat is in the files this touches, so you can go straight to a place rather than reading "
    "the whole file:\n\n{map}\n"
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
HOW_TO_RUN = (
    "\n\nThis system's tests are run with exactly this command, from {built}:\n\n    {tests}\n\n"
    "Use it. To run less than all of it, keep the command and put the paths or names on the end. "
    "Do not go looking for an interpreter, a virtual environment or a test runner — this is the "
    "one that works here, and anything you find by searching is a guess about a fact you have "
    "already been given."
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

    done = subprocess.run(f"{tests} --collect-only", shell=True, cwd=str(built),
                          capture_output=True, text=True, check=False)
    return sorted({line.strip() for line in done.stdout.splitlines() if "::" in line})


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
            expect: int = 1, wants: str = "*.json") -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    if blind:
        instruction += BLIND
    return {"instruction": instruction + HOW_TO_READ.format(scratch=scratch),
            "waiting_for": str(out), "expect": expect, "wants": wants}


def next_item(order: dict[str, object], work: Path) -> dict[str, object] | None:
    """The earliest round first, and inside a round the smallest piece of work."""

    for item in sorted(order["work"], key=lambda w: (w["round"], w["part_count"],
                                                     str(w["requirement_id"]))):
        if not (work / f"build-{item['requirement_id']}" / "done.json").exists():
            return item
    return None


#: What a streamed tool event is worth saying. A tool's own arguments say more about what the agent
#: is doing than any summary of them would: the file it opened, the pattern it searched for, the
#: command it ran. Anything longer than this is the agent's prose, and the prose is in its log.
def _what_it_did(event: dict[str, object]) -> str | None:
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


def _watch(stream, work: Path, job: str) -> None:
    """Say what the agent does, line by line, while it does it."""

    for line in stream:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        did = _what_it_did(event)
        if did:
            say(work, "agent", job=job, doing=did)


#: A definition, at the start of a line or one indent in. Deliberately crude: this is a map for
#: somebody who is going to open the file anyway, not an index anybody parses.
_DEFINED = re.compile(r"^(?: {4})?(?:async def |def |class )(\w+)")


def _map_of(built: Path, files: set[str]) -> str:
    """Every function in the files this job touches, with the line it starts on.

    A builder given one sentence and a five-thousand-line file reads that file over and over
    looking for the place — six times on the job that made this necessary, the same file each
    time, because nothing carries between reads. The file is a quarter of a million characters;
    the list of what is in it and where is four thousand. Handing over the map costs nothing and
    replaces the search.

    It is a map, not an answer: it says where things are, never which one is wrong.
    """

    maps = []
    for name in sorted(files):
        path = built / name
        if not path.is_file() or path.suffix != ".py":
            continue
        found = [
            f"  {number}: {match.group(1)}"
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1)
            if (match := _DEFINED.match(line))
        ]
        if found:
            maps.append(f"{name} ({len(found)} definitions):\n" + "\n".join(found))
    return "\n\n".join(maps)


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


def drive(order: dict[str, object], work: Path, built: Path, tests: str) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
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
    parts = "\n".join(f"- {p['part']}" for p in item["parts"])
    named_parts = "\n".join(f"- [{p['part_id']}] {p['part']}" for p in item["parts"])

    say(work, "item taken up", item=rid, parts=len(item["parts"]),
        attempt=len(sorted(out.glob("refused-*.json"))) + 1)

    # 1 · what passes now, recorded before anything is touched.
    before_path = out / "tests-before.json"
    if not before_path.exists():
        with _timed(work, "tests before the change", item=rid):
            before_path.write_text(json.dumps(_failures(built, tests), indent=2), encoding="utf-8")
    before = json.loads(before_path.read_text(encoding="utf-8"))
    say(work, "tests before the change read", item=rid, already_failing=len(before["failed"]))

    # 2 · the change. A refused attempt is moved aside so the builder is asked again, carrying what
    # the readers objected to. Without this the step returned 'not built' and handed back nothing,
    # and the whole order stalled on the first honest refusal.
    change_path = out / "change.json"
    refused = sorted(out.glob("refused-*.json"))
    if not change_path.exists():
        instruction = BUILD.format(
            built=built, requirement=item["requirement"], parts=parts, out=out,
        ) + HOW_TO_RUN.format(built=built, tests=tests)
        # Where the readers who put this item on the list said they looked. They cited a file and
        # a line for every part; the order carried none of it, so each builder searched a
        # five-thousand-line file again for a place already written down.
        seen_at = "\n".join(
            f"- {p['part_id']}: {_still_at(built, str(p['seen_at']))}"
            for p in item["parts"] if p.get("seen_at")
        )
        if seen_at:
            instruction += SEEN_AT.format(seen_at=seen_at)
        drawn = _map_of(built, {
            str(p["seen_at"]).split(":")[0] for p in item["parts"] if p.get("seen_at")
        })
        if drawn:
            instruction += MAP.format(map=drawn)
        ruling = rulings.get(rid)
        if ruling:
            instruction += RULED.format(ruling=ruling)
        if refused:
            last = json.loads(refused[-1].read_text(encoding="utf-8"))
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
            "already_failing_before_the_change": len(before["failed"]),
            "work": [_packet(
                instruction, out, out.parent / f"build-{rid}-scratch", blind=False,
                wants="change.json",
            )],
        }
    change = json.loads(change_path.read_text(encoding="utf-8"))

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
        kept = out / f"refused-{len(refused) + 1}.json"
        kept.write_text(json.dumps({
            "item": rid, "requirement": item["requirement"], "attempt": len(refused) + 1,
            "what_changed": change.get("what_changed"), "left_alone": change.get("left_alone"),
            "objections": ["the builder changed nothing: "
                           + str(change.get("what_changed") or "")[:600]],
            "built": False,
        }, indent=2), encoding="utf-8")
        change_path.unlink()
        say(work, "builder changed nothing", item=rid, attempt=len(refused) + 1,
            because=str(change.get("what_changed"))[:200])
        if len(refused) + 1 >= ATTEMPTS:
            return {
                "stopped": "the builder changed nothing, every attempt", "item": rid,
                "requirement": item["requirement"], "attempts": len(refused) + 1,
                "the_builder_says": change.get("what_changed"),
                "for_a_person": "Only the owner can settle this. Put their answer in "
                                "rulings.json under this item.",
                "work": [],
            }
        return drive(order, work, built, tests)

    # 3 · the same question, asked again, by two readers who cannot see each other.
    waiting = []
    for index in range(1, PASSES + 1):
        checked = work / f"check-{rid}-{index}"
        if _answers_in(checked) < len(item["parts"]):
            waiting.append(_packet(
                VERIFY.format(built=built, named_parts=named_parts, out=checked)
                + HOW_TO_RUN.format(built=built, tests=tests),
                checked, work / f"check-{rid}-{index}-scratch", blind=True,
                expect=len(item["parts"]),
            ))
    if waiting:
        say(work, "change in hand, handing it to the checkers", item=rid,
            changed=change["files"], checkers=len(waiting))
        return {"stopped": "checking the change", "item": rid, "changed": change["files"],
                "work": waiting}

    # 4 · the verdict. Nothing that passed before may fail now, and both readers must say yes.
    with _timed(work, "tests after the change", item=rid):
        after = _failures(built, tests)
    (out / "tests-after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    broke = sorted(set(after["failed"]) - set(before["failed"]))
    # A test that no longer exists cannot fail, so the gate above cannot see it go. This is not a
    # judgement about whether the removal was right — it is the removal being written down.
    gone = sorted(set(before.get("names") or []) - set(after.get("names") or []))

    # One answer per part per pass, and every one of them yes. Counting distinct answers instead
    # of answers-per-pass is how the first run of this step passed a part that only one reader had
    # answered: the two readers had named the same sentence differently, so each name carried a
    # single 'yes' and the set of answers looked unanimous.
    said: dict[str, list[str]] = {}
    for index in range(1, PASSES + 1):
        for path in sorted((work / f"check-{rid}-{index}").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            said.setdefault(str(record.get("part_id")), []).append(str(record.get("answer")))
    wanted = {str(p["part_id"]) for p in item["parts"]}
    unproven = sorted(pid for pid in wanted
                      if said.get(pid, []).count("yes") < PASSES)
    missing = sorted(pid for pid in wanted if pid not in said)
    unnamed = sorted(set(said) - wanted)

    verdict = {
        "item": rid,
        "requirement": item["requirement"],
        "changed": change["files"],
        "what_changed": change.get("what_changed"),
        "left_alone": change.get("left_alone"),
        "tests_that_broke": broke,
        "tests_that_stopped_existing": gone,
        "removals_the_builder_declared": [
            str(row.get("test")) for row in (change.get("tests_changed") or [])
            if isinstance(row, dict)
        ],
        "parts_both_readers_call_true": sorted(wanted - set(unproven)),
        "parts_not_agreed": unproven,
        "parts_no_reader_answered": missing,
        "answers_under_a_name_no_part_has": unnamed,
        "built": not broke and not unproven and not missing and not unnamed,
    }
    if verdict["built"]:
        (out / "done.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        return verdict

    # Refused. Keep everything — the change stays in place and the reading stays on disk — but
    # record why, set this attempt aside, and let the next run hand it back to a builder.
    objections = []
    for index in range(1, PASSES + 1):
        for path in sorted((work / f"check-{rid}-{index}").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if str(record.get("answer")) != "yes":
                objections.append(
                    f"{record.get('part_id')}: {record.get('looked_at') or 'no reason given'}"
                )
    if broke:
        objections.append("these tests passed before the change and fail after it: "
                          + ", ".join(broke))

    attempt = len(refused) + 1
    verdict["attempt"] = attempt
    verdict["objections"] = objections
    (out / f"refused-{attempt}.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    change_path.rename(out / f"change-{attempt}.json")
    for index in range(1, PASSES + 1):
        checked = work / f"check-{rid}-{index}"
        if checked.is_dir():
            checked.rename(work / f"check-{rid}-{index}-attempt-{attempt}")

    if attempt >= ATTEMPTS:
        verdict["for_a_person"] = (
            f"{attempt} attempts have been refused. What is being asked may not be buildable as "
            "stated, or the sentences may be describing something the system does elsewhere."
        )
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

    parts = shlex.split(command)
    started = []

    def run(number: int, job: dict[str, object]) -> dict[str, object]:
        # Wait for the work, not for the process. On the first long unattended run a builder wrote
        # its change and its own record and then stayed alive: nineteen minutes later the loop had
        # not moved, because it was waiting on a process that had already done everything asked of
        # it. What the next step reads is what is on disk, so that is what waiting means here.
        log = work / f"launch-{tag}-{number}.log"
        waiting_for = Path(str(job["waiting_for"]))
        wanted = int(job.get("expect") or 1)
        pattern = str(job.get("wants") or "*.json")
        started = subprocess.Popen(
            parts, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(built), text=True,
        )
        started.stdin.write(str(job["instruction"]))
        started.stdin.close()

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
        watching = threading.Thread(target=_watch, args=(started.stdout, work, f"{tag}-{number}"),
                                    daemon=True)
        watching.start()

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

        out, err = started.communicate()
        log.write_text((out or "") + ("\n--- stderr ---\n" + err if err else "")
                       + ("\n--- it had already written its answer and was still running; "
                          "the step stopped waiting\n" if delivered else ""), encoding="utf-8")
        wrote = _delivered(waiting_for, pattern)
        say(work, "agent finished", job=f"{tag}-{number}", wrote=wrote, of=wanted,
            minutes=round((time.monotonic() - began) / 60, 1),
            exit_code=started.returncode, stopped_after_delivering=delivered)
        return {"exit_code": started.returncode, "log": str(log),
                "stopped_after_delivering": delivered, "wrote": wrote}

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
        ordering = run.drive(args.report.resolve(), work, 550, 0.15)
        while ordering.get("work"):
            if not args.reader_command:
                return _say({"stopped": "reading the pairs, and no reader command was given",
                             "work": ordering["work"]})
            _launch(ordering["work"], args.reader_command, built, work, "order")
            ordering = run.drive(args.report.resolve(), work, 550, 0.15)
        if not ordering.get("order"):
            return _say(ordering)
        args.order = Path(ordering["order"])

    order = json.loads(args.order.read_text(encoding="utf-8"))

    if not args.reader_command:
        print(json.dumps(drive(order, work, built, args.tests), indent=2))
        return 0

    # The brake. An unattended loop with no cap is the one way this can do harm at a speed nobody
    # sees, so it stops at --items, and it stops the moment a round of reading leaves the step
    # exactly where it was — a reader that wrote nothing would otherwise be asked forever.
    settled, rounds, stuck, seen = [], 0, 0, None
    while True:
        result = drive(order, work, built, args.tests)
        if "built" in result:
            settled.append({"item": result.get("item"), "built": result.get("built")})
            say(work, "verdict", item=result.get("item"), built=result.get("built"),
                done_so_far=sum(1 for row in settled if row["built"]), of=args.items,
                why=result.get("why") or result.get("not_built"))
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
