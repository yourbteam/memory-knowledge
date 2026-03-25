from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger()

_WARNING_AGE_DAYS = 9  # warn if last_refresh > 9 days old (token lifetime is 10 days)


async def codex_token_provider(auth_path: str) -> str:
    """Read access_token from Codex CLI's auth.json."""
    path = Path(auth_path).expanduser()
    if not path.exists():
        raise RuntimeError(
            f"Codex auth file not found at {path} — run 'codex auth' to authenticate"
        )

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Codex auth file at {path} is malformed — run 'codex auth' to re-authenticate"
        )

    tokens = data.get("tokens")
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError(
            "Codex auth.json has no OAuth tokens — run 'codex auth' to authenticate"
        )

    # Warn if token is likely stale
    last_refresh = data.get("last_refresh")
    if last_refresh:
        try:
            refreshed_at = datetime.fromisoformat(last_refresh)
            age_days = (datetime.now(timezone.utc) - refreshed_at).days
            if age_days >= _WARNING_AGE_DAYS:
                logger.warning(
                    "codex_token_stale",
                    age_days=age_days,
                    hint="Run 'codex auth' to refresh",
                )
        except (ValueError, TypeError):
            pass

    return tokens["access_token"]
