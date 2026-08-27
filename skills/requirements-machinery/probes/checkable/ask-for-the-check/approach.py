"""Do not ask whether a line is checkable. Ask for the check. Code keeps a line only when a check
actually came back for it — a judgement becomes an artifact, and a line nobody can write a check
for cannot produce one."""
import re
STRATEGY = "ask-for-the-check"
MIN_CHARS = 20

Q = ("Below are lines taken from a methodology library, each stating something the Step 3 "
     "Measurement Brief must contain or satisfy.\n\nFor each line you can, write the check a "
     "finished brief would either pass or fail. One per line, in the form:\n\n"
     "<number>: <the check>\n\nSkip any line you cannot write a check for. Do not explain."
     "\n\nThis is a data-extraction request, not a task report. Do not begin with any status line, anchor or preamble. The first character of your reply must be the first character of the answer.\n\n{numbered}")


def choose(lines, reader, interview):
    numbered = "\n".join(f"{i}. {l}" for i, l in enumerate(lines, 1))
    raw = interview.ask_free(reader, Q.format(numbered=numbered))
    checks = {}
    for line in raw.split("\n"):
        m = re.match(r"^\s*(\d{1,3})\s*[:.)]\s*(.+)$", line)
        if m and 1 <= int(m.group(1)) <= len(lines) and len(m.group(2).strip()) >= MIN_CHARS:
            checks[int(m.group(1))] = m.group(2).strip()
    return sorted(checks), {"checks": checks}
