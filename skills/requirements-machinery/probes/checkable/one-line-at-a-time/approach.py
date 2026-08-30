"""Each line asked on its own, through the code interview, which states the permitted values and
refuses anything else."""
STRATEGY = "one-line-at-a-time"
CHOICES = ["YES", "NO"]

Q = ("Below is one line taken from a methodology library. It states something the Step 3 "
     "Measurement Brief must contain or satisfy.\n\nCould you write a check that a finished brief "
     "would either pass or fail against this line?\n\n--- LINE ---\n{line}\n--- END LINE ---")


def choose(lines, reader, interview):
    keep, seats = [], []
    for i, line in enumerate(lines, 1):
        answer, transcript = interview.ask_choice(reader, Q.format(line=line), CHOICES)
        seats.append({"n": i, "answer": answer, "attempts": len(transcript)})
        if answer == "YES":
            keep.append(i)
    return keep, {"per_line": seats}
