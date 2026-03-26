from __future__ import annotations

import re
from typing import Any

# These are the EXACT same patterns from retrieval.py's classify_prompt.
# Moved here for reusability while preserving behavioral equivalence.

EXACT_PATTERNS = re.compile(
    r"\b[a-z]+[A-Z][a-zA-Z]*\b"  # camelCase (getUserById)
    r"|\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b"  # PascalCase (UserService)
    r"|[a-zA-Z_]+\.[a-zA-Z_]+\.[a-zA-Z_]+"  # dotted path (foo.bar.baz)
    r'|"[^"]+"'  # quoted identifiers
    r"|'[^']+'"
)

IMPACT_KEYWORDS = {"impact", "affect", "change", "break", "breaking", "depends"}
PATTERN_KEYWORDS = {"pattern", "how does", "approach", "design", "architecture"}
DECISION_KEYWORDS = {"decision", "why did", "history", "chose", "rationale"}


def extract_prompt_features(query: str) -> dict[str, Any]:
    """Extract features from a prompt for routing decisions.

    Returns a feature dict describing the prompt characteristics.
    Used internally by classify_prompt — the public classification interface.
    """
    q = query.lower()
    tokens = q.split()

    identifiers = EXACT_PATTERNS.findall(query)
    identifier_density = len(identifiers) / max(len(tokens), 1)

    has_impact = any(kw in q for kw in IMPACT_KEYWORDS)
    has_decision = any(kw in q for kw in DECISION_KEYWORDS)
    has_pattern = any(kw in q for kw in PATTERN_KEYWORDS)

    return {
        "identifier_count": len(identifiers),
        "identifier_density": round(identifier_density, 3),
        "has_impact_keywords": has_impact,
        "has_decision_keywords": has_decision,
        "has_pattern_keywords": has_pattern,
        "token_count": len(tokens),
        "has_quoted_strings": bool(re.search(r'["\']', query)),
    }
