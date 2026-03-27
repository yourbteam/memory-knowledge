from __future__ import annotations

import re
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings

logger = structlog.get_logger()

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

STACK_TRACE_PATTERN = re.compile(
    r"Traceback|File\s+\"[^\"]+\",\s+line\s+\d+|at\s+\w+\.\w+\s*\(",
    re.IGNORECASE,
)
SQL_KEYWORDS_PATTERN = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE)\b",
    re.IGNORECASE,
)
TRAVERSAL_PHRASES = {"what calls", "depends on", "callers of", "called by", "who uses", "imports of"}


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
        "has_stack_trace": bool(STACK_TRACE_PATTERN.search(query)),
        "has_sql_keywords": bool(SQL_KEYWORDS_PATTERN.search(query)),
        "has_traversal_phrases": any(phrase in q for phrase in TRAVERSAL_PHRASES),
    }


async def match_archetype(
    query: str,
    qdrant_client: AsyncQdrantClient | None,
    settings: Settings,
) -> dict[str, Any] | None:
    """Match a query against routing archetypes via semantic search.

    Returns the best-matching archetype payload if score >= 0.75, else None.
    """
    if qdrant_client is None:
        return None

    from memory_knowledge.llm.openai_client import embed_single

    try:
        query_embedding = await embed_single(query, settings)
        results = await qdrant_client.search(
            collection_name="routing_archetypes",
            query_vector=query_embedding,
            limit=1,
            score_threshold=0.75,
        )
        if results:
            payload = dict(results[0].payload or {})
            payload["archetype_score"] = results[0].score
            return payload
    except Exception:
        logger.debug("archetype_match_failed", exc_info=True)

    return None
