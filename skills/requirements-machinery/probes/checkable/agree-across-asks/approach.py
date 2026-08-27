"""Ask N times, keep only what every ask returns."""
import re
STRATEGY = "agree-across-asks"
ASKS = 3

Q = ("Below are lines taken from a methodology library, each stating something the Step 3 "
     "Measurement Brief must contain or satisfy.\n\nFor which of them could you write a check that "
     "a finished brief would either pass or fail?\n\nReply with the numbers only, one per line."
     "\n\nThis is a data-extraction request, not a task report. Do not begin with any status line, anchor or preamble. The first character of your reply must be the first character of the answer.\n\n{numbered}")


def _nums(raw, upper):
    return {int(m.group(1)) for m in (re.match(r"^\s*(\d{1,3})\s*[.):]?\s*$", l)
            for l in raw.split("\n")) if m and 1 <= int(m.group(1)) <= upper}


def choose(lines, reader, interview):
    numbered = "\n".join(f"{i}. {l}" for i, l in enumerate(lines, 1))
    sets = [_nums(interview.ask_free(reader, Q.format(numbered=numbered)), len(lines))
            for _ in range(ASKS)]
    keep = set.intersection(*sets) if sets else set()
    return sorted(keep), {"per_ask": [sorted(s) for s in sets]}
