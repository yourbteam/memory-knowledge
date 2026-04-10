from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import structlog

from memory_knowledge.config import Settings

logger = structlog.get_logger()

_GITHUB_API_BASE = "https://api.github.com"
_CONFIG_REQUIRED_KEYS = ("org", "app_id", "installation_id", "pem_path")
_auth_registry: "GitHubAuthRegistry | None" = None


@dataclass(frozen=True)
class GitHubAppSettings:
    github_app_id: str
    github_app_installation_id: str
    github_app_pem_path: str
    github_app_config_path: str


class GitHubAppAuth:
    def __init__(self, git_settings: GitHubAppSettings):
        self._app_id = git_settings.github_app_id
        self._installation_id = git_settings.github_app_installation_id
        self._pem_path = os.path.expanduser(git_settings.github_app_pem_path)
        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    def is_configured(self) -> bool:
        return bool(
            self._app_id
            and self._installation_id
            and os.path.isfile(self._pem_path)
        )

    def _generate_jwt(self) -> str:
        import jwt

        now = int(time.time())
        payload = {
            "iss": self._app_id,
            "iat": now - 60,
            "exp": now + 600,
        }
        try:
            with open(self._pem_path, "r", encoding="utf-8") as f:
                private_key = f.read()
        except OSError as exc:
            raise RuntimeError(
                f"Cannot read GitHub App PEM key at {self._pem_path}: {exc}"
            ) from exc
        return jwt.encode(payload, private_key, algorithm="RS256")

    async def _request_installation_token(self, app_jwt: str) -> dict:
        url = f"{_GITHUB_API_BASE}/app/installations/{self._installation_id}/access_tokens"

        def _do_request() -> dict:
            req = urllib.request.Request(
                url,
                data=b"",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "memory-knowledge/1.0",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                raise RuntimeError(
                    f"GitHub API returned HTTP {exc.code} for installation token "
                    f"(app_id={self._app_id}, installation_id={self._installation_id}): {body}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Network error requesting GitHub installation token: {exc.reason}"
                ) from exc

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_request)

    async def get_installation_token(self) -> str:
        async with self._lock:
            now = datetime.now(timezone.utc)
            if (
                self._cached_token
                and self._token_expires_at
                and (self._token_expires_at - now).total_seconds() > 300
            ):
                return self._cached_token

            app_jwt = self._generate_jwt()
            result = await self._request_installation_token(app_jwt)
            if "token" not in result or "expires_at" not in result:
                raise RuntimeError(
                    f"Unexpected GitHub API response: missing 'token' or 'expires_at' "
                    f"(keys: {list(result.keys())})"
                )

            self._cached_token = result["token"]
            self._token_expires_at = datetime.fromisoformat(
                result["expires_at"].replace("Z", "+00:00")
            )
            return self._cached_token

    @staticmethod
    def get_clone_url(org: str, repo: str, token: str) -> str:
        return f"https://x-access-token:{token}@github.com/{org}/{repo}.git"


class GitHubAuthRegistry:
    def __init__(self):
        self._by_org: dict[str, GitHubAppAuth] = {}
        self._default: GitHubAppAuth | None = None

    def register(self, org: str, auth: GitHubAppAuth) -> None:
        self._by_org[org.lower()] = auth

    def set_default(self, auth: GitHubAppAuth) -> None:
        self._default = auth

    def get(self, org: str) -> GitHubAppAuth | None:
        return self._by_org.get(org.lower()) or self._default

    def is_configured(self) -> bool:
        return any(a.is_configured() for a in self._by_org.values()) or (
            self._default is not None and self._default.is_configured()
        )


def build_auth_registry(settings: Settings) -> GitHubAuthRegistry:
    registry = GitHubAuthRegistry()
    config_path = os.path.expanduser(settings.github_app_config_path)
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                configs = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("github_app_config_read_failed", path=config_path, error=str(exc))
            configs = None
        if isinstance(configs, list) and configs:
            for entry in configs:
                if not isinstance(entry, dict):
                    continue
                missing = [k for k in _CONFIG_REQUIRED_KEYS if not entry.get(k)]
                if missing:
                    logger.warning(
                        "github_app_config_entry_skipped",
                        org=entry.get("org", "?"),
                        missing=missing,
                    )
                    continue
                auth = GitHubAppAuth(
                    GitHubAppSettings(
                        github_app_id=str(entry["app_id"]),
                        github_app_installation_id=str(entry["installation_id"]),
                        github_app_pem_path=str(entry["pem_path"]),
                        github_app_config_path=config_path,
                    )
                )
                registry.register(str(entry["org"]), auth)
    return registry


def init_github_auth_registry(settings: Settings) -> GitHubAuthRegistry:
    global _auth_registry
    _auth_registry = build_auth_registry(settings)
    return _auth_registry


def _parse_github_org_repo(origin_url: str) -> tuple[str, str] | None:
    parts = urlsplit(origin_url)
    if parts.hostname != "github.com":
        return None
    path = parts.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    bits = path.split("/")
    if len(bits) != 2 or not bits[0] or not bits[1]:
        return None
    return bits[0], bits[1]


async def get_authenticated_git_url(origin_url: str, settings: Settings) -> str:
    parsed = _parse_github_org_repo(origin_url)
    if parsed is None:
        return origin_url

    if settings.github_access_token:
        from memory_knowledge.git.clone import _inject_github_token

        return _inject_github_token(
            origin_url,
            settings.github_access_token,
            default_username=settings.github_https_username,
        )

    registry = _auth_registry or build_auth_registry(settings)
    org, repo = parsed
    auth = registry.get(org)
    if auth is None or not auth.is_configured():
        return origin_url

    token = await auth.get_installation_token()
    return GitHubAppAuth.get_clone_url(org, repo, token)
