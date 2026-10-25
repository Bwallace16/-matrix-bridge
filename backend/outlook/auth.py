"""Token acquisition. MSAL device flow for headless boxes, cache on disk."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable, Protocol

from .config import OutlookSettings


class TokenProvider(Protocol):
    def access_token(self) -> str: ...


class StaticTokenProvider:
    """Hands back a fixed token. Tests and one-off scripts."""

    def __init__(self, token: str):
        self._token = token

    def access_token(self) -> str:
        return self._token


class AuthRequired(RuntimeError):
    """No cached account. Run the device flow once."""


class MsalTokenProvider:
    """Delegated tokens for one signed-in user, persisted in a serializable cache."""

    def __init__(self, settings: OutlookSettings, prompt: Callable[[str], None] | None = None):
        import msal  # imported lazily so tests without msal still load the package

        if not settings.client_id:
            raise AuthRequired("OUTLOOK_CLIENT_ID is not set")
        self._settings = settings
        self._prompt = prompt or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self._cache_path: Path = settings.state_dir / "token_cache.json"
        self._cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            self._cache.deserialize(self._cache_path.read_text())
        if settings.client_secret:
            self._app = msal.ConfidentialClientApplication(
                settings.client_id,
                client_credential=settings.client_secret,
                authority=settings.authority,
                token_cache=self._cache,
            )
        else:
            self._app = msal.PublicClientApplication(
                settings.client_id, authority=settings.authority, token_cache=self._cache
            )

    def _persist(self) -> None:
        if self._cache.has_state_changed:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(self._cache.serialize())
            os.chmod(self._cache_path, 0o600)

    def has_account(self) -> bool:
        return bool(self._app.get_accounts())

    def access_token(self) -> str:
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(self._settings.scopes, account=accounts[0])
            self._persist()
            if result and "access_token" in result:
                return result["access_token"]
        raise AuthRequired("No cached sign-in. Run: python -m outlook auth")

    def login_device_flow(self) -> dict:
        """Interactive once. Prints the code, waits for the browser sign-in, caches the result."""
        flow = self._app.initiate_device_flow(scopes=self._settings.scopes)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed to start: {json.dumps(flow)}")
        self._prompt(flow["message"])
        result = self._app.acquire_token_by_device_flow(flow)
        self._persist()
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description") or result.get("error") or "sign-in failed")
        claims = result.get("id_token_claims") or {}
        return {
            "name": claims.get("name"),
            "username": claims.get("preferred_username"),
            "scopes": result.get("scope", "").split(),
        }

    def logout(self) -> None:
        for account in self._app.get_accounts():
            self._app.remove_account(account)
        self._persist()
