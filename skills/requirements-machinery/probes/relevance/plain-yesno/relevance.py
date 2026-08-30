"""Relevance: plain yes-or-no, taken through a code interview."""
STRATEGY = "plain-yesno"
NEEDS_QUOTE = False

QUESTION = (
    "Below is one page of a corporate communications methodology library.\n\n"
    "The target document is: {target}\n\n"
    "Does this page contain anything that constrains what that document must contain, must say, or "
    "must be checked against?\n\n"
    "--- PAGE ---\n{page}\n--- END PAGE ---"
)
CHOICES = ["YES", "NO"]
