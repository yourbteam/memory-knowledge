"""Take a determinate answer from a model the way the harness already does it.

The model is shown the question, the exact permitted answers, and nothing else it may return. An
answer outside that set is refused with a message naming what would satisfy it, and the question is
asked again. Every rejected attempt is kept.

Prompting is not enforcement. This is the enforcement.
"""
import json
import os
import re
import subprocess
import time

ATTEMPTS = 3
READER_TIMEOUT_ENV = "REQ_MACHINERY_READER_TIMEOUT_SECONDS"
DEFAULT_READER_TIMEOUT_SECONDS = 180.0

_seq = 0


def _feed(event, **fields):
    """One line per reader call, appended to the feed the caller names in REQ_MACHINERY_FEED.

    Every reader call in this machinery flows through this module, so this one seam is the whole
    telemetry fix: on 2026-08-23 a pass's progress between its start and finish events had to be
    proven from process churn, because four separate call sites had no per-call record. Four call
    sites found, one boundary fixed. No feed named, no file written — the machinery never invents
    a path.
    """
    global _seq
    _seq += 1
    path = os.environ.get("REQ_MACHINERY_FEED")
    if not path:
        return
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps({"seq": _seq, "at": round(time.time(), 1),
                                 "event": event, **fields}) + "\n")
    except OSError:
        pass


_policy_checked = {}


class ValidatedReaderCommand(str):
    """A policy-checked command identity that carries its exact spawn arguments."""

    def __new__(cls, raw, argv):
        value = super().__new__(cls, raw)
        value.argv = tuple(argv)
        return value


def validate_reader_command(reader_command):
    """The installed-client boundary. The canonical machinery is provider-neutral: with no
    client-model-policy.json beside this file, the command runs as given. An installed client
    projection adds that file, and then the check is fail-closed: the command must be exactly
    the projection's named minimum, and a refusal names that minimum — before any reader is
    spent, since the same command fails on the very first ask."""
    if isinstance(reader_command, ValidatedReaderCommand):
        return reader_command
    if reader_command in _policy_checked:
        return _policy_checked[reader_command]
    parts = reader_command.split()
    if not parts:
        raise SystemExit("reader command is empty")
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "client-model-policy.json")
    if os.path.exists(path):
        try:
            policy = json.load(open(path))
            client = policy["client"]
            required = policy["required_runtime"].split()
            recommended = policy["recommended_reader_command"]
            if (policy["schema_version"] != 1 or policy["fail_closed"] is not True
                    or not client or not required or not recommended):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid client model policy: {path}") from exc
        if parts[:len(required)] != required or parts != recommended.split():
            raise SystemExit(
                f"the {client} projection refuses reader command {reader_command!r}; "
                f"use exactly this minimum command: {recommended}")
    identity = ValidatedReaderCommand(reader_command, parts)
    _policy_checked[reader_command] = identity
    return identity


def _argv(reader_command):
    return list(validate_reader_command(reader_command).argv)


def _raw_log(name, out):
    """Lossless stdout and stderr of one reader call, kept beside the feed. The state records
    keep 120 characters of a reply; on 2026-08-25 the two slow calls of a 621-call run and the
    full text of a coerced reply were unrecoverable because nothing kept the rest."""
    path = os.environ.get("REQ_MACHINERY_FEED")
    if not path:
        return None
    try:
        raw_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "raw")
        os.makedirs(raw_dir, exist_ok=True)
        with open(os.path.join(raw_dir, name), "wb") as fh:
            fh.write(b"--- stdout ---\n" + out.stdout + b"\n--- stderr ---\n" + out.stderr)
        return name
    except OSError:
        return None


def _reader_timeout():
    """Return the declared per-reader execution bound, rejecting unsafe configuration."""
    raw = os.environ.get(READER_TIMEOUT_ENV, str(DEFAULT_READER_TIMEOUT_SECONDS))
    try:
        value = float(raw)
    except ValueError as exc:
        raise SystemExit(f"{READER_TIMEOUT_ENV} must be a number") from exc
    if value <= 0 or value > 3600:
        raise SystemExit(f"{READER_TIMEOUT_ENV} must be greater than 0 and at most 3600")
    return value


def _completed(stdout=b"", stderr=b""):
    """Give timeout captures the same shape as CompletedProcess for private raw logging."""
    return subprocess.CompletedProcess([], 124, stdout=stdout or b"", stderr=stderr or b"")


def _spawn(reader_command, prompt, kind, **labels):
    """The one place a reader process is started. Three spawn sites found in this file when the
    feed landed; three routed through here, so no ask of any kind is invisible. Callers pass
    stage/piece/seat labels so a feed event is attributable to the work it did — the 2026-08-25
    audit could not say which stage a 134-second call belonged to."""
    argv = _argv(reader_command)
    started = time.time()
    try:
        out = subprocess.run(
            argv, input=prompt.encode(), capture_output=True, timeout=_reader_timeout())
    except subprocess.TimeoutExpired as exc:
        out = _completed(exc.stdout, exc.stderr)
        raw_name = _raw_log(f"ask-{os.getpid()}-{time.monotonic_ns()}.log", out)
        _feed("ask", kind=kind, outcome="timeout", exit_code=124,
              ms=int((time.time() - started) * 1000), question_chars=len(prompt), reply_chars=0,
              **({"raw": raw_name} if raw_name else {}),
              **{k: v for k, v in labels.items() if v is not None})
        print("reader execution timed out before producing a semantic answer", file=os.sys.stderr)
        raise SystemExit(4) from exc
    reply = out.stdout.decode("utf-8", "replace").strip()
    # Named by pid + monotonic nanoseconds, not by _seq: every stage module loads its own copy
    # of this module, so _seq restarts per instance and a seq-based name silently overwrote
    # earlier calls' logs (5 asks, 3 files, first proof run of this fix). The feed event carries
    # the name, so the pairing survives the uglier filename.
    raw_name = _raw_log(f"ask-{os.getpid()}-{time.monotonic_ns()}.log", out)
    outcome = "zero-exit" if out.returncode == 0 else "nonzero-exit"
    _feed("ask", kind=kind, outcome=outcome, exit_code=out.returncode,
          ms=int((time.time() - started) * 1000),
          question_chars=len(prompt), reply_chars=len(reply),
          **({"raw": raw_name} if raw_name else {}),
          **{k: v for k, v in labels.items() if v is not None})
    if out.returncode != 0:
        print("reader execution failed before producing a semantic answer", file=os.sys.stderr)
        raise SystemExit(4)
    return reply


def ask_free(reader_command, question, **labels):
    """One ask, the reply returned whole. Used where the answer is not one of a fixed set of
    values and code checks it afterwards instead — a quote against its page, a line number against
    the units code itself produced. Where the answer must be one of a known set, ask_choice is the
    one to use: it states the permitted values and refuses anything else."""
    if not reader_command:
        return ""
    reply = _spawn(reader_command, question, "free", **labels)
    _feed("reader reply", kind="free", outcome="valid-reply",
          **{k: v for k, v in labels.items() if v is not None})
    return reply


def ask_choice(reader_command, question, choices, *, attempts=ATTEMPTS, preserve_raw=False, **labels):
    """Returns (answer, transcript). answer is one of choices, or None if none was ever given."""
    allowed = ", ".join(choices)
    transcript = []
    prompt = (
        f"{question}\n\n"
        f"Answer with exactly one of these values and nothing else: {allowed}\n"
        f"Your entire reply must be that one value, on its own, with no heading, preamble, "
        f"explanation or punctuation."
    )
    for attempt in range(1, attempts + 1):
        if not reader_command:
            return None, transcript
        raw = _spawn(reader_command, prompt, "attempt", **labels)
        value = _match(raw, choices)
        transcript_row = {"attempt": attempt, "raw_first_line": raw.split("\n")[0][:120],
                          "accepted": value}
        if preserve_raw:
            transcript_row["raw_reply"] = raw
        transcript.append(transcript_row)
        if value is not None:
            _feed("reader reply", kind="choice", outcome="valid-reply", attempt=attempt,
                  **{k: v for k, v in labels.items() if v is not None})
            return value, transcript
        _feed("reader reply", kind="choice", outcome="malformed-reply", attempt=attempt,
              **{k: v for k, v in labels.items() if v is not None})
        prompt = (
            f"That answer was refused: it was not one of the permitted values.\n"
            f"You replied: {raw.splitlines()[0][:120] if raw else '(nothing)'}\n\n"
            f"{question}\n\n"
            f"Reply with exactly one of: {allowed}. Nothing before it, nothing after it."
        )
    return None, transcript


def _match(raw, choices):
    """A reply counts only if one permitted value stands alone on some line of it.

    Deliberately strict, and tested against real reply shapes:

        'YES'                          accepted
        'YES.'  '"NO"'  'yes'          accepted — punctuation and case are not the answer
        'directives=...\n\nYES'        accepted — a header above the answer does not hide it,
                                       which is the failure that started this
        'Based on the page:\nYES'      accepted
        'YES, because the page ...'    REFUSED
        'The answer is YES'            REFUSED

    A value buried in a sentence is refused rather than fished out, because "not YES" and "YES
    would be wrong" both contain YES. The refusal restates the requirement and asks again, which
    costs one call; guessing wrong costs a wrong answer nobody can see.
    """
    for line in raw.split("\n"):
        candidate = line.strip().strip('"').rstrip(".").upper()
        for choice in choices:
            if candidate == choice.upper():
                return choice
    return None


def _candidates(raw):
    """Every span of the reply that could be a quote, longest first.

    ask_choice is deliberately strict because a permitted value buried in prose is unsafe to fish
    out — "not YES" contains YES. A quote is the opposite case: quotecheck verifies it character
    for character against the page, so a span that verifies IS the page's own words no matter what
    surrounded it. Strictness here bought nothing and cost everything. Taking only the first line
    of the reply meant that when the reader answered

        directives=working-agreement/DIRECTIVES.md@2026-08-03; mode=Research; ...

        1. "No research starts until the brief and the measurement brief are approved in writing."
        2. "the mandatory Measurement Brief (baseline, target, source, owner - see Step 10)."

    the header was tested, failed, and six verbatim quotes below it were never looked at. Three
    attempts, three refusals, and a yes downgraded to no-answer on a page the reader had read
    correctly every time.
    """
    out = []
    for m in re.finditer(r'[\"\u201c]([^\"\u201d]{4,})[\"\u201d]', raw):
        out.append(m.group(1))
    for line in raw.split("\n"):
        line = re.sub(r'^\s*(?:[-*\u2022]|\d+[.)])\s*', "", line).strip().strip('"\u201c\u201d')
        if line:
            out.append(line)
    seen, uniq = set(), []
    for c in sorted(out, key=len, reverse=True):
        if c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


NO_WORDS_REPLY = "NO SUCH WORDS"

_ESCAPE_LINE = (
    f"If the page does not contain such words, reply with exactly: {NO_WORDS_REPLY}"
)


def _denies(raw):
    """True when the reader stated, in the offered exact form, that the words are not on the
    page. Matched line-alone with _match's strictness: a token buried in a sentence is not the
    answer."""
    return _match(raw, [NO_WORDS_REPLY]) is not None


def ask_quote(reader_command, question, page_text, quotecheck, *, attempts=ATTEMPTS, **labels):
    """Ask for words that are on the page, and refuse anything that is not.

    Every span of the reply is offered to quotecheck and the longest that verifies wins. A short
    fragment is not enough: a handful of common words appears on almost any page, so a span must
    pass the shared quotecheck grounding floor before it counts as grounding anything.

    The reader always has an honest way out. On the Step 5 production run (2026-08-25, pieces
    p-0004 and p-0005) readers that answered "None. The page contains no words that…" were
    re-asked with "Copy the words exactly" until they surrendered a sentence, and a piece both
    readers had disclaimed landed as fully grounded. Now every ask offers NO_WORDS_REPLY as an
    exact permitted answer; giving it ends the retry immediately, the denial is recorded, and
    the caller's verdict logic sees no quote — the yes-without-words outcome that was designed
    for exactly this.
    """
    transcript = []
    prompt = (
        f"{question}\n\n"
        f"Reply with the exact words copied from the page and nothing else.\n"
        f"{_ESCAPE_LINE}"
    )
    for attempt in range(1, attempts + 1):
        if not reader_command:
            return None, transcript
        raw = _spawn(reader_command, prompt, "attempt", **labels)
        if _denies(raw):
            transcript.append({"attempt": attempt, "raw_first_line": raw.split("\n")[0][:120],
                               "denied": True, "accepted": None})
            _feed("reader reply", kind="quote", outcome="valid-reply", attempt=attempt,
                  **{k: v for k, v in labels.items() if v is not None})
            return None, transcript
        tried = _candidates(raw)
        hit = next((grounded for c in tried
                    if (grounded := quotecheck.grounding(c, page_text)) is not None), None)
        transcript.append({"attempt": attempt, "raw_first_line": raw.split("\n")[0][:120],
                           "candidates_tried": len(tried), "accepted": hit})
        if hit:
            _feed("reader reply", kind="quote", outcome="valid-reply", attempt=attempt,
                  **{k: v for k, v in labels.items() if v is not None})
            return hit, transcript
        _feed("reader reply", kind="quote", outcome="malformed-reply", attempt=attempt,
              **{k: v for k, v in labels.items() if v is not None})
        prompt = (
            f"That answer was refused: none of it was found on the page.\n"
            f"Nothing in your reply of {len(tried)} line(s) matched the page character for character.\n\n"
            f"{question}\n\n"
            f"Copy the words exactly as they appear on the page.\n"
            f"{_ESCAPE_LINE}"
        )
    return None, transcript
