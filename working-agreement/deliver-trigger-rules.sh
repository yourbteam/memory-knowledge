#!/usr/bin/env bash
# PreToolUse delivery: put the governing rule in front of the model at the instant the
# situation it governs arises.
#
# Why this exists: the always-on file can only carry short pass/fail rules before it
# becomes wallpaper, and the corpus retrieves by word-similarity, so a rule arrives when
# the topic sounds related rather than when the situation is real. On 2026-07-28 a commit
# ran without the registered-sequence rule surfacing at all, on the one turn it governed.
#
# Contract: stdin is the PreToolUse JSON. A matching call is refused once per trigger per
# session with the rule text taken live from DIRECTIVES.md; the same call passes when
# re-issued. Refusal is the channel because it is the only PreToolUse path that reliably
# reaches the model. Any internal error allows the call, so a defect here cannot wedge a
# session.
set -uo pipefail

DIRECTIVES="${MK_DIRECTIVES_PATH:-/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md}"
TRIGGERS="${MK_TRIGGER_RULES_PATH:-/Users/kamenkamenov/memory-knowledge/working-agreement/trigger-rules.json}"
STATE_DIR="${MK_TRIGGER_STATE_DIR:-/private/tmp/directive-trigger-state}"

payload="$(cat)" || exit 0

python3 - "$payload" "$DIRECTIVES" "$TRIGGERS" "$STATE_DIR" <<'PY'
import hashlib, json, os, re, shlex, sys

RUNNER_PREFIXES = {"sudo", "env", "command", "nohup", "time", "exec", "builtin"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
OPERATORS = {";", "&&", "||", "|", "&", "|&"}
# Programs whose first operand names what is really being run: an interpreter's script,
# a multiplexer's subcommand. For anything else an operand is data — `grep foo` searches
# for foo, it does not run it.
INTERPRETERS = SHELLS | {"python", "python3", "node", "ruby", "perl", "osascript"}
SUBCOMMAND_TOOLS = {
    "git", "npm", "pnpm", "yarn", "uv", "cargo", "docker", "make", "brew",
    "pip", "pip3", "kubectl", "gh", "poetry",
}


def _strip_heredocs(text):
    """Drop heredoc bodies. They are data handed to a program, not commands to run."""
    for opener in re.finditer(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", text):
        body = re.search(
            rf"\n.*?\n[ \t]*{re.escape(opener.group(2))}[ \t]*(?=\n|$)",
            text[opener.end():],
            re.S,
        )
        if body:
            start = opener.end() + body.start()
            text = text[:start] + "\n" + text[opener.end() + body.end():]
    return text


def _newlines_to_separators(text):
    """A newline ends a command only outside quotes; inside one it is just content."""
    out, quote, escaped = [], None, False
    for char in text:
        if escaped:
            out.append(char)
            escaped = False
            continue
        if char == "\\" and quote != "'":
            out.append(char)
            escaped = True
            continue
        if quote:
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "\n":
            out.append(";")
            continue
        out.append(char)
    return "".join(out)


def command_heads(command, depth=0):
    """The leading tokens of every command this line will actually execute.

    Matching the raw string fires a rule whenever its words appear anywhere in the
    payload, including inside a quoted argument — which is how a test fixture carrying
    the text `git commit` was flagged as a commit on 2026-07-28. Delivering rules on
    calls they do not govern teaches the model to skim past the refusal, so the match
    has to be about what runs, not about what the text contains.
    """
    if depth > 2:
        return []
    lexer = shlex.shlex(
        _newlines_to_separators(_strip_heredocs(command)),
        posix=True, punctuation_chars=True,
    )
    lexer.whitespace_split = True
    segments, current = [], []
    for token in lexer:                      # may raise on unbalanced quotes
        if token in OPERATORS:
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)

    heads = []
    for tokens in segments:
        while tokens and (
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0], re.S)
            or tokens[0] in RUNNER_PREFIXES
        ):
            tokens = tokens[1:]
        if not tokens:
            continue
        heads.append(" ".join(_head_tokens(tokens)))
        if tokens[0].rsplit("/", 1)[-1] in SHELLS and "-c" in tokens[1:]:
            index = tokens.index("-c")
            if index + 1 < len(tokens):
                heads.extend(command_heads(tokens[index + 1], depth + 1))
    return heads


def _head_tokens(tokens):
    """The tokens that say what runs: the program, its flags, and its one real operand."""
    program = tokens[0]
    takes_operand = program.rsplit("/", 1)[-1] in (INTERPRETERS | SUBCOMMAND_TOOLS)
    head, operand_taken, skip_next = [program], False, False
    for token in tokens[1:]:
        if len(head) >= 5:
            break
        if skip_next:                    # an inline script body is code, not a command
            skip_next = False
            continue
        if " " in token or "\t" in token:  # a command word never contains whitespace
            continue
        if token == "-c":
            head.append(token)
            skip_next = True
        elif token.startswith("-"):
            head.append(token)
        elif takes_operand and not operand_taken:
            head.append(token)
            operand_taken = True
    return head

try:
    event = json.loads(sys.argv[1])
    directives_path, triggers_path, state_dir = sys.argv[2], sys.argv[3], sys.argv[4]
    triggers = json.load(open(triggers_path, encoding="utf-8"))["triggers"]
except Exception:
    raise SystemExit(0)

tool = event.get("tool_name") or ""
tool_input = event.get("tool_input") or {}
payload_text = json.dumps(tool_input)
session = event.get("session_id") or "-"

# What each trigger is matched against. A shell call is matched against the commands it
# will run; anything else against its raw input. A command that cannot be tokenized
# falls back to the raw string, so a parsing gap under-blocks nothing.
subjects = [payload_text]
if tool == "Bash" and isinstance(tool_input.get("command"), str):
    try:
        subjects = command_heads(tool_input["command"]) or [""]
    except ValueError:
        subjects = [tool_input["command"]]


def tools_of(trigger):
    named = trigger.get("tools") or ([trigger["tool"]] if trigger.get("tool") else [])
    return set(named)


match = None
for trigger in triggers:
    wanted = tools_of(trigger)
    if wanted and tool not in wanted:
        continue
    against = [payload_text] if trigger.get("match") == "raw" else subjects
    try:
        if any(re.search(trigger["pattern"], subject) for subject in against):
            match = trigger
            break
    except re.error:
        continue

if match is None:
    raise SystemExit(0)


def claim(name):
    """Take a once-only marker. True the first time, False every time after."""
    path = os.path.join(state_dir, name)
    if os.path.exists(path):
        return False
    try:
        os.makedirs(state_dir, exist_ok=True)
        open(path, "w").close()
    except OSError:
        return False
    return True


if match.get("on") == "repeat":
    # G19's "same fingerprint twice": the second identical invocation is the signal,
    # because an identical command is normally re-issued only after the first failed.
    digest = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()[:16]
    if claim(f"{session}.seen.{digest}"):
        raise SystemExit(0)      # first time: remember it, say nothing

if not claim(f"{session}.{match['id']}"):
    raise SystemExit(0)          # already delivered this session; do not nag

def rule_body(rule_id):
    """The rule as it is written right now, so delivery can never carry a stale copy."""
    try:
        text = open(directives_path, encoding="utf-8").read()
    except OSError:
        return None
    start = re.search(rf"^## {re.escape(rule_id)} .*$", text, re.M)
    if not start:
        return None
    rest = text[start.start():]
    end = re.search(r"^\*\*Set:\*\*.*$", rest, re.M)
    return rest[: end.end()] if end else rest[:2000]

wanted_rules = match.get("rules", [])
bodies = [body for body in (rule_body(r) for r in wanted_rules) if body]
if not bodies:
    # Silence here would consume the trigger's one shot and govern nothing, which looks
    # exactly like compliance. Report the broken table instead.
    sys.stderr.write(
        f"Trigger '{match['id']}' matched this {tool} call, but none of the rules it "
        f"names ({', '.join(wanted_rules) or 'none'}) could be read from the directives "
        "file. The delivery table references a rule that no longer exists under that id. "
        "Repair trigger-rules.json before continuing.\n"
    )
    raise SystemExit(2)

sys.stderr.write(
    f"Before this {tool} call — the rules that govern it:\n\n"
    + "\n\n".join(bodies)
    + f"\n\n{match.get('note', '')}\n\n"
    "Re-issue the call once you have acted on the above.\n"
)
raise SystemExit(2)
PY
