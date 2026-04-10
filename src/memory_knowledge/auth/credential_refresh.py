"""Codex OAuth token refresh with Azure Key Vault seeding/writeback.

Adapted from mcp-agents-workflow's credential_refresh.py. Provides:
- Automatic Codex token refresh via OpenAI OAuth endpoint
- Azure Key Vault seeding on startup (pull tokens from KV)
- Key Vault writeback after successful refresh (push updated tokens)
- Background refresh loop (daily at configurable UTC hour)
- File locking for safe concurrent access to auth.json
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import tempfile
import time
from datetime import timedelta
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()

# ── Codex OAuth constants ─────────────────────────────────────────────

_CODEX_OAUTH_URL = "https://auth.openai.com/oauth/token"
_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_KV_SECRET_NAME = "cli-auth-codex"


# ── File I/O helpers ──────────────────────────────────────────────────

def _read_json_file(path: str) -> dict | None:
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("read_json_failed", path=path, error=str(e))
        return None


def _atomic_write_json(path: str, data: dict) -> None:
    path = os.path.expanduser(path)
    dir_path = os.path.dirname(path)
    os.makedirs(dir_path, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)
    except Exception:
        os.unlink(temp_path)
        raise


def _atomic_write_text(path: str, data: str) -> None:
    path = os.path.expanduser(path)
    dir_path = os.path.dirname(path)
    os.makedirs(dir_path, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(temp_path, path)
    except Exception:
        os.unlink(temp_path)
        raise


def _locked_update_json(
    path: str, fallback_data: dict, updater, label: str
) -> tuple[bool, str | None]:
    """Acquire file lock, re-read, apply updater, write atomically."""
    path = os.path.expanduser(path)
    lock_path = path + ".lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        return False, f"{label} file is locked by another process"

    try:
        fresh = _read_json_file(path) or fallback_data
        updater(fresh)
        _atomic_write_json(path, fresh)
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


# ── HTTP helper ───────────────────────────────────────────────────────

class CredentialRefreshError(Exception):
    pass


async def _http_post_form(url: str, data: dict, retries: int = 3) -> dict:
    loop = asyncio.get_running_loop()
    for attempt in range(retries):
        try:
            def _do_request():
                req = urllib.request.Request(
                    url,
                    data=urllib.parse.urlencode(data).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())

            return await loop.run_in_executor(None, _do_request)
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            if 400 <= e.code < 500:
                raise CredentialRefreshError(f"HTTP {e.code}: {body}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
        except (urllib.error.URLError, OSError) as e:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise CredentialRefreshError(f"Network error: {e}")
    raise CredentialRefreshError("Max retries exceeded")


# ── Codex token refresh ──────────────────────────────────────────────

def parse_codex_last_refresh(path: str) -> datetime | None:
    data = _read_json_file(path)
    if not data:
        return None
    try:
        ts = data.get("last_refresh")
        if ts:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except (TypeError, ValueError):
        pass
    # Fall back to file mtime
    try:
        path = os.path.expanduser(path)
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except OSError:
        return None


async def refresh_codex_token(path: str) -> tuple[bool, str | None]:
    """Refresh Codex OAuth token via OpenAI endpoint.

    Returns (success, error_message).
    """
    data = _read_json_file(path)
    if not data:
        return False, f"Cannot read {path}"

    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return False, "No tokens object in Codex credentials"
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return False, "No refresh_token in Codex credentials"

    try:
        resp = await _http_post_form(_CODEX_OAUTH_URL, {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _CODEX_CLIENT_ID,
        })
    except CredentialRefreshError as e:
        return False, str(e)

    if "access_token" not in resp:
        return False, "OAuth response missing 'access_token'"

    def _apply_update(fresh: dict) -> None:
        if "tokens" not in fresh:
            fresh["tokens"] = {}
        fresh["tokens"]["access_token"] = resp["access_token"]
        if "refresh_token" in resp:
            fresh["tokens"]["refresh_token"] = resp["refresh_token"]
        fresh["OPENAI_API_KEY"] = resp["access_token"]
        fresh["last_refresh"] = datetime.now(timezone.utc).isoformat()

    try:
        success, error = _locked_update_json(path, data, _apply_update, "Codex")
        if success:
            logger.info("codex_token_refreshed")
        return success, error
    except (KeyError, TypeError) as e:
        return False, f"Unexpected response format: {e}"
    except OSError as e:
        return False, f"File lock error: {e}"


# ── Key Vault integration ────────────────────────────────────────────

async def fetch_kv_secret(vault_name: str, secret_name: str) -> str | None:
    """Fetch a single secret value from Azure Key Vault. Returns None on failure."""
    if not _keyvault_available():
        return None

    loop = asyncio.get_running_loop()

    def _fetch():
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        vault_url = f"https://{vault_name}.vault.azure.net"
        kv_token = os.environ.get("AZURE_KEYVAULT_TOKEN")
        if kv_token:
            from azure.core.credentials import AccessToken

            class _StaticTokenCredential:
                def get_token(self, *scopes, **kwargs):
                    return AccessToken(kv_token, int(time.time()) + 3600)
                def close(self):
                    pass

            credential = _StaticTokenCredential()
        else:
            credential = DefaultAzureCredential()

        client = SecretClient(vault_url=vault_url, credential=credential)
        try:
            secret = client.get_secret(secret_name)
            return secret.value
        finally:
            client.close()
            credential.close()

    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        logger.warning("kv_secret_fetch_failed", secret_name=secret_name, error=str(e))
        return None


def _keyvault_available() -> bool:
    try:
        import azure.identity  # noqa: F401
        import azure.keyvault.secrets  # noqa: F401
        return True
    except ImportError:
        return False


async def seed_from_keyvault(
    vault_name: str, codex_auth_path: str, force: bool = False
) -> str:
    """Pull Codex credentials from Azure Key Vault and write to local file.

    Returns status: "seeded", "skipped", or "error: ...".
    """
    if not _keyvault_available():
        return "skipped (azure SDK not installed)"

    loop = asyncio.get_running_loop()

    def _fetch_secret():
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        vault_url = f"https://{vault_name}.vault.azure.net"
        kv_token = os.environ.get("AZURE_KEYVAULT_TOKEN")
        if kv_token:
            from azure.core.credentials import AccessToken

            class _StaticTokenCredential:
                def get_token(self, *scopes, **kwargs):
                    return AccessToken(kv_token, int(time.time()) + 3600)
                def close(self):
                    pass

            credential = _StaticTokenCredential()
        else:
            credential = DefaultAzureCredential()

        client = SecretClient(vault_url=vault_url, credential=credential)
        try:
            secret = client.get_secret(_KV_SECRET_NAME)
            return {
                "value": secret.value,
                "updated_on": secret.properties.updated_on,
            }
        finally:
            client.close()
            credential.close()

    try:
        secret_data = await loop.run_in_executor(None, _fetch_secret)
    except Exception as e:
        return f"error: {e}"

    value = secret_data.get("value")
    if not value or value == "{}":
        return "skipped (empty placeholder)"

    # Check if local file is newer
    if not force:
        local_refresh = parse_codex_last_refresh(codex_auth_path)
        kv_updated = secret_data.get("updated_on")
        if local_refresh and kv_updated and local_refresh > kv_updated:
            return "skipped (local is newer)"

    try:
        cred_data = json.loads(value)
        _atomic_write_json(codex_auth_path, cred_data)
        # Create config.toml for Codex CLI
        config_dir = os.path.dirname(os.path.expanduser(codex_auth_path))
        config_path = os.path.join(config_dir, "config.toml")
        os.makedirs(config_dir, exist_ok=True)
        with open(config_path, "w") as f:
            f.write('[auth]\ncli_auth_credentials_store = "file"\n')
        logger.info("codex_credentials_seeded_from_keyvault")
        return "seeded"
    except (json.JSONDecodeError, OSError) as e:
        return f"error: {e}"


async def seed_github_app_secrets_from_keyvault(
    vault_name: str,
    github_app_config_path: str,
    *,
    config_secret_name: str = "github-app-config",
) -> str:
    """Seed GitHub App config + PEMs from Azure Key Vault."""
    if not _keyvault_available():
        return "skipped (azure SDK not installed)"

    loop = asyncio.get_running_loop()
    config_path = os.path.expanduser(github_app_config_path)

    def _fetch_and_write() -> str:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        vault_url = f"https://{vault_name}.vault.azure.net"
        kv_token = os.environ.get("AZURE_KEYVAULT_TOKEN")
        if kv_token:
            from azure.core.credentials import AccessToken

            class _StaticTokenCredential:
                def get_token(self, *scopes, **kwargs):
                    return AccessToken(kv_token, int(time.time()) + 3600)

                def close(self):
                    pass

            credential = _StaticTokenCredential()
        else:
            credential = DefaultAzureCredential()

        client = SecretClient(vault_url=vault_url, credential=credential)
        try:
            secret = client.get_secret(config_secret_name)
            value = secret.value
            if not value:
                return "skipped (empty placeholder)"

            configs = json.loads(value)
            if not isinstance(configs, list):
                return "error: github-app-config is not a JSON array"

            github_dir = os.path.dirname(config_path)
            for entry in configs:
                pem_secret = entry.get("pem_secret")
                if not pem_secret:
                    continue
                pem_local_path = os.path.join(github_dir, f"{pem_secret}.pem")
                pem_obj = client.get_secret(pem_secret)
                if not pem_obj.value:
                    continue
                _atomic_write_text(pem_local_path, pem_obj.value)
                os.chmod(os.path.expanduser(pem_local_path), 0o600)
                entry["pem_path"] = pem_local_path

            _atomic_write_text(config_path, json.dumps(configs, indent=2))
            os.chmod(os.path.expanduser(config_path), 0o600)
            return "seeded+enriched"
        finally:
            client.close()
            credential.close()

    try:
        return await loop.run_in_executor(None, _fetch_and_write)
    except Exception as e:
        return f"error: {e}"


async def writeback_to_keyvault(vault_name: str, codex_auth_path: str) -> str:
    """Push local Codex credentials back to Azure Key Vault.

    Returns status: "written", "skipped", or "error: ...".
    """
    if not _keyvault_available():
        return "skipped (azure SDK not installed)"

    data = _read_json_file(codex_auth_path)
    if not data:
        return "error: cannot read local credentials"

    loop = asyncio.get_running_loop()

    def _write_secret():
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        vault_url = f"https://{vault_name}.vault.azure.net"
        kv_token = os.environ.get("AZURE_KEYVAULT_TOKEN")
        if kv_token:
            from azure.core.credentials import AccessToken

            class _StaticTokenCredential:
                def get_token(self, *scopes, **kwargs):
                    return AccessToken(kv_token, int(time.time()) + 3600)
                def close(self):
                    pass

            credential = _StaticTokenCredential()
        else:
            credential = DefaultAzureCredential()

        client = SecretClient(vault_url=vault_url, credential=credential)
        try:
            client.set_secret(_KV_SECRET_NAME, json.dumps(data, separators=(",", ":")))
        finally:
            client.close()
            credential.close()

    try:
        await loop.run_in_executor(None, _write_secret)
        logger.info("codex_credentials_written_to_keyvault")
        return "written"
    except Exception as e:
        return f"error: {e}"


# ── Background refresh manager ───────────────────────────────────────

class CodexTokenManager:
    """Background manager that refreshes Codex tokens on a schedule.

    - Checks token age every `check_interval` seconds
    - Triggers refresh if token is older than `refresh_after_days`
    - Runs a daily refresh at `daily_refresh_utc_hour`
    - Seeds from Key Vault on startup if configured
    - Writes back to Key Vault after successful refresh
    """

    def __init__(
        self,
        codex_auth_path: str = "~/.codex/auth.json",
        keyvault_name: str | None = None,
        check_interval: int = 300,
        refresh_after_days: int = 6,
        daily_refresh_utc_hour: int = 5,
        writeback_enabled: bool = True,
    ):
        self.codex_auth_path = codex_auth_path
        self.keyvault_name = keyvault_name
        self.check_interval = check_interval
        self.refresh_after_days = refresh_after_days
        self.daily_refresh_utc_hour = daily_refresh_utc_hour
        self.writeback_enabled = writeback_enabled
        self._stop_event = asyncio.Event()
        self._check_task: asyncio.Task | None = None
        self._daily_task: asyncio.Task | None = None
        self._consecutive_failures = 0
        self._refresh_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start background refresh loops. Optionally seed from Key Vault."""
        if self.keyvault_name:
            status = await seed_from_keyvault(
                self.keyvault_name, self.codex_auth_path
            )
            logger.info("keyvault_seed_result", status=status)

        self._check_task = asyncio.create_task(self._check_loop())
        self._daily_task = asyncio.create_task(self._daily_loop())
        logger.info(
            "codex_token_manager_started",
            check_interval=self.check_interval,
            refresh_after_days=self.refresh_after_days,
            daily_hour=self.daily_refresh_utc_hour,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        for task in [self._check_task, self._daily_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("codex_token_manager_stopped")

    async def _check_loop(self) -> None:
        """Periodically check token expiry and refresh proactively."""
        while not self._stop_event.is_set():
            try:
                # Check actual JWT expiry, not just file age
                expires_soon = self._token_expires_within(
                    self.codex_auth_path, buffer_seconds=600
                )
                if expires_soon:
                    logger.info("codex_token_expiring_soon", buffer_seconds=600)
                    await self._do_refresh()
                else:
                    # Fall back to age-based check
                    last_refresh = parse_codex_last_refresh(self.codex_auth_path)
                    if last_refresh:
                        age_days = (datetime.now(timezone.utc) - last_refresh).days
                        if age_days >= self.refresh_after_days:
                            await self._do_refresh()
            except Exception as e:
                logger.error("codex_check_failed", error=str(e))

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.check_interval
                )
                break  # stop_event was set
            except asyncio.TimeoutError:
                pass  # normal timeout, continue loop

    async def _daily_loop(self) -> None:
        """Run a refresh at a fixed UTC hour daily."""
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            target = now.replace(
                hour=self.daily_refresh_utc_hour,
                minute=0, second=0, microsecond=0,
            )
            if target <= now:
                target = target + timedelta(days=1)
            wait_seconds = (target - now).total_seconds()

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=wait_seconds
                )
                break  # stop_event was set
            except asyncio.TimeoutError:
                pass  # time to refresh

            logger.info("daily_codex_refresh_triggered")
            await self._do_refresh()

    @staticmethod
    def _token_expires_within(auth_path: str, buffer_seconds: int = 600) -> bool:
        """Check if the access_token JWT expires within buffer_seconds."""
        import base64
        data = _read_json_file(auth_path)
        if not data:
            return True
        tokens = data.get("tokens", {})
        for key in ("access_token", "id_token"):
            token = tokens.get(key)
            if not token:
                continue
            try:
                payload = token.split(".")[1]
                payload += "=" * (4 - len(payload) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload))
                exp = claims.get("exp")
                if exp and time.time() > (exp - buffer_seconds):
                    return True
                if exp:
                    return False
            except (IndexError, ValueError, json.JSONDecodeError):
                continue
        return True  # no parseable expiry found, assume stale

    async def _do_refresh(self) -> None:
        if self._refresh_lock.locked():
            logger.debug("refresh_skipped_lock_held")
            return
        async with self._refresh_lock:
            await self._do_refresh_inner()

    async def _do_refresh_inner(self) -> None:
        success, error = await refresh_codex_token(self.codex_auth_path)
        if success:
            self._consecutive_failures = 0
            if self.writeback_enabled and self.keyvault_name:
                wb_status = await writeback_to_keyvault(
                    self.keyvault_name, self.codex_auth_path
                )
                logger.info("keyvault_writeback_result", status=wb_status)
        else:
            self._consecutive_failures += 1
            logger.error(
                "codex_refresh_failed",
                error=error,
                consecutive_failures=self._consecutive_failures,
            )
            # Try reseeding from KV on failure
            if self._consecutive_failures >= 2 and self.keyvault_name:
                reseed_status = await seed_from_keyvault(
                    self.keyvault_name, self.codex_auth_path, force=True
                )
                logger.info("keyvault_reseed_on_failure", status=reseed_status)
