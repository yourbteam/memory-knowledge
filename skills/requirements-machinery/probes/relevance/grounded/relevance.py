"""Relevance: grounded — the yes must come with the page's own words, checked against the page."""
STRATEGY = "grounded"
NEEDS_QUOTE = True

QUESTION = (
    "Below is one page of a corporate communications methodology library.\n\n"
    "The target document is: {target}\n\n"
    "Does this page contain anything that constrains what that document must contain, must say, or "
    "must be checked against?\n\n"
    "--- PAGE ---\n{page}\n--- END PAGE ---"
)
QUOTE_QUESTION = (
    "You said this page constrains {target}.\n\n"
    "Quote the exact words from the page that do it.\n\n"
    "--- PAGE ---\n{page}\n--- END PAGE ---"
)
CHOICES = ["YES", "NO"]
