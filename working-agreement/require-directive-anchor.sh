#!/usr/bin/env bash
# Stop gate: refuse to end a turn whose reply does not open with a well-formed G0 anchor.
#
# Why this exists: G0 is the one rule delivered in full on every turn, and the anchor is
# the artifact that makes every other rule's status checkable. On 2026-07-28 six
# consecutive replies carried no anchor at all — the messages had grown short and
# conversational and it was dropped as overhead. Nothing noticed. The directive-read gate
# added the same day forces the rules to be read; it cannot tell whether they are
# followed. The anchor is the first line of every reply, so it can be checked mechanically.
#
# Contract: stdin is the Stop JSON. Exit 0 lets the turn end; exit 2 blocks it and returns
# the stderr text to the model, which then re-sends with the anchor. Honours
# stop_hook_active so a correction loop can never wedge. Any internal error lets the turn
# end, so a defect here can never trap a session.
set -uo pipefail

payload="$(cat)" || exit 0

python3 - "$payload" <<'PY'
import json, re, sys

# `why=` and `serves=` were added on 2026-08-06. Kamen, after a day in which five real fixes
# left the goal's number exactly where it started: "Before you do something and after you have
# done it I need you to report to me why do you chose to do it and how does it serve the goal."
# `why=` is the reason for THIS action; `serves=` is the line from the declared goal it moves,
# and "does not serve it" is a legitimate and sometimes necessary answer -- what is refused is
# acting without saying either.
REQUIRED = ("mode=", "controller=", "envelope=", "ask=", "words=", "scope=", "exceptions=",
            "proof=", "why=", "serves=")

try:
    event = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(0)

if event.get("stop_hook_active"):
    raise SystemExit(0)

path = event.get("transcript_path")
if not path:
    raise SystemExit(0)

try:
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
except OSError:
    raise SystemExit(0)

def tool_uses(entry):
    """Every tool call in an assistant turn, as (name, input) pairs."""
    message = entry.get("message") or {}
    content = message.get("content")
    if entry.get("type") != "assistant" or not isinstance(content, list):
        return []
    return [
        (block.get("name"), block.get("input") or {})
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def is_turn_start(entry):
    """True only for something Kamen actually typed.

    Tool results are recorded as ``type: "user"`` entries too. Treating them as turn
    boundaries reset the turn after every tool call, so the edit and action checks only
    ever saw what happened after the LAST tool result -- which is nothing. On 2026-07-28
    that silently disabled the envelope-vs-edits check and refused a turn that had
    launched two background processes.
    """
    if entry.get("type") != "user" or entry.get("isCompactSummary"):
        return False
    content = ((entry.get("message") or {}).get("content"))
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


def reply_text(entry):
    """The visible prose of an assistant turn, ignoring tool calls and thinking."""
    message = entry.get("message") or {}
    if entry.get("type") != "assistant" or message.get("role") != "assistant":
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    joined = "".join(parts).strip()
    return joined or None

entries = []
for raw in lines:
    raw = raw.strip()
    if not raw:
        continue
    try:
        entries.append(json.loads(raw))
    except Exception:
        continue

# Where each playbook was last invoked, where the context was last reset, and which
# files this turn edited that earlier turns had already edited. The controller and
# direction claims are checked against these rather than trusted.
loaded = {}
last_reset = -1
edits_this_turn = []
actions_this_turn = []
edits_before = {}
for index, entry in enumerate(entries):
    if entry.get("isCompactSummary"):
        # A reset drops the loaded playbook's instructions. A controller named from
        # before it is a claim about something no longer in context: on 2026-07-28
        # every turn after the third reset still named a controller last invoked
        # 154 entries earlier, and nothing noticed.
        last_reset = index
    if is_turn_start(entry):
        for path in edits_this_turn:
            edits_before.setdefault(path, index)
        edits_this_turn = []
        actions_this_turn = []
    for name, payload in tool_uses(entry):
        if name == "Skill" and isinstance(payload.get("skill"), str):
            loaded[payload["skill"]] = index
        elif name in {"Edit", "Write", "NotebookEdit"}:
            edits_this_turn.append(payload.get("file_path") or "?")
            actions_this_turn.append("edit")
        elif name == "Bash":
            # A launched process is the only other thing that outlives the turn.
            actions_this_turn.append("background run")

# A file this turn edits that an earlier turn already edited is, on its face, not the
# first issue of its kind — the router requires direction-check before Write-code takes
# one. Nothing enforced that, and on 2026-07-28 it was skipped on exactly such a re-edit.
repeat_edits = sorted({path for path in edits_this_turn if path in edits_before})
direction_stale = [
    path for path in repeat_edits
    if loaded.get("direction-check", -1) < edits_before[path]
]

text, text_index = None, -1
for index in range(len(entries) - 1, -1, -1):
    found = reply_text(entries[index])
    if found:
        text, text_index = found, index
        break

if text is None:
    raise SystemExit(0)

# The transcript can lag the reply this hook is meant to judge. When the newest
# assistant text predates the newest user entry, the reply is not visible yet and the
# only text available belongs to an earlier turn -- judging it pairs one turn's words
# with another turn's actions. On 2026-07-28 that produced three refusals of correct
# replies, including an ask=none complaint about a message that said ask=approval.
last_user = max(
    (index for index, entry in enumerate(entries) if is_turn_start(entry)),
    default=-1,
)
if text_index < last_user:
    raise SystemExit(0)

first = next((line.strip() for line in text.splitlines() if line.strip()), "")
missing = [field for field in REQUIRED if field not in first]

# G0 requires the anchor to be the TURN'S first text. A later text block is mid-turn
# narration, and judging it as though it were the reply refused correct turns twice on
# 2026-07-28. So: the turn must open with an anchor, and the per-message checks below
# apply to the newest text only when that text is itself anchored.
turn_opener = next(
    (
        reply_text(entries[index])
        for index in range(last_user + 1, len(entries))
        if reply_text(entries[index])
    ),
    None,
)
opener_line = next(
    (line.strip() for line in (turn_opener or "").splitlines() if line.strip()), ""
)
problem = None
if not opener_line.startswith("directives="):
    problem = "the turn does not open with the directive anchor"
elif not first.startswith("directives="):
    raise SystemExit(0)
elif missing:
    problem = "the anchor is missing: " + ", ".join(f.rstrip("=") for f in missing)
else:
    match = re.search(r"controller=([^;]+)", first)
    claimed = [
        name.strip()
        for name in re.split(r"->|→|,", match.group(1) if match else "")
        if name.strip()
    ]
    named = [name for name in claimed if name not in {"none", "n/a"}]
    unloaded = [name for name in named if name not in loaded]
    stale = [name for name in named if loaded.get(name, -1) < last_reset]
    if unloaded:
        # The whole point of naming a controller is that it changed what was done. A
        # name that was never invoked is a claim of rigour that was not applied.
        problem = (
            "the anchor names a playbook that was never invoked in this session: "
            + ", ".join(unloaded)
            + ". Invoke it, or write controller=none"
        )
    elif stale:
        problem = (
            "the anchor names a controller last invoked before the context was reset: "
            + ", ".join(stale)
            + ". Its instructions are no longer loaded — invoke it again, or write "
            "controller=none"
        )
    elif direction_stale:
        problem = (
            "this turn edits a file an earlier turn already edited ("
            + ", ".join(sorted({p.rsplit("/", 1)[-1] for p in direction_stale})[:3])
            + "), so it is not the first issue of its kind. The router requires "
            "direction-check before Write-code takes one. Run it, then re-send"
        )
    elif re.search(r"envelope=none", first) and edits_this_turn:
        # G0 calls this out by name: envelope=none while applying product-code edits is
        # a self-declared G11 violation. It happened twice on 2026-07-27, both times
        # because momentum carried past the pre-edit check rather than through it.
        problem = (
            "the anchor says no envelope is approved, but this turn edited "
            + ", ".join(sorted(set(edits_this_turn))[:3])
            + ". Freeze an envelope before editing"
        )
    elif not named and edits_this_turn:
        problem = (
            "the anchor says no controller is running, but this turn edited "
            + ", ".join(sorted(set(edits_this_turn))[:3])
        )
    elif re.search(r"ask=none", first) and not actions_this_turn:
        # G31: a turn that asks for nothing must leave work in flight. The turn ends
        # where the message ends, so a closing sentence like "starting it now" is a
        # promise about a turn that has not begun -- and only Kamen can begin it. On
        # 2026-07-28 that pattern repeated until he named it. Only an applied edit or
        # a launched background process outlives the turn, so only those count.
        problem = (
            "the anchor says ask=none, which claims work is in flight, but this turn "
            "applied no edit and launched nothing. Do the next thing before sending, "
            "or ask for what you need"
        )

if problem is None:
    # G29's cap, measured rather than declared. The prose Kamen reads is everything
    # except the anchor and any fenced code; declaring a number under the cap while the
    # message runs long makes the field decoration, which is what it replaced.
    body = "\n".join(text.splitlines()[1:])
    body = re.sub(r"```.*?```", " ", body, flags=re.S)
    body = re.sub(r"`[^`]*`", " ", body)
    real = len(re.findall(r"[^\s]+", body))
    asking = re.search(r"ask=(decision|approval)", first)
    declared_match = re.search(r"words=(\d+)", first)
    declared = int(declared_match.group(1)) if declared_match else None
    if asking and real > 150:
        problem = (
            f"this message asks Kamen to decide and runs to {real} words. "
            "G29 caps it at 150. Cut it, do not restate it"
        )
    elif declared is not None and real > declared * 1.15 + 5:
        problem = (
            f"the anchor declares {declared} words; the message is {real}. "
            "The count is a number Kamen can check, so it has to be true"
        )

if problem is None:
    raise SystemExit(0)

sys.stderr.write(
    f"Blocked: {problem}.\n\n"
    "G0 requires every substantive reply to open with one line:\n"
    "  directives=<artifact>; mode=<mode>; controller=<controller|none>; "
    "envelope=<approved:\"<outcome>\"|none|n/a>; ask=<none|decision|approval>; "
    "words=<N>; scope=<scope>; exceptions=<none or conflict>; "
    "proof=<real-path evidence|none:<what-is-untested>|n/a>\n\n"
    "`proof=` answers ONE question: what exercised this through the path it will actually take?\n"
    "  proof=state.validate+round-trip        the real save accepted it\n"
    "  proof=live:round-5-opening-count       observed in a live run\n"
    "  proof=none:unit-only                   the piece passes; the path is untested\n"
    "  proof=n/a                              this message claims nothing works\n"
    "`none:` is an honest and frequent answer. On 2026-08-01 three claims — an armed timer\n"
    "that never fired, a gate whose inputs were never traced, and a durable write the record\n"
    "rejected — would each have had to carry `proof=none:` in front of Kamen.\n\n"
    "Re-send the same reply with that line first.\n"
)
raise SystemExit(2)
PY
