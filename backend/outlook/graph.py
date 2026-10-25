"""Thin Microsoft Graph client: auth header, paging, delta rounds, throttling."""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable

import httpx

from .auth import TokenProvider

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
RETRY_STATUSES = {429, 502, 503, 504}


class GraphError(RuntimeError):
    def __init__(self, status: int, message: str, url: str = ""):
        super().__init__(f"Graph {status}: {message} ({url})")
        self.status = status
        self.message = message
        self.url = url


class GraphClient:
    def __init__(
        self,
        tokens: TokenProvider,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        max_retries: int = 4,
        page_size: int = 50,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._tokens = tokens
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._max_retries = max_retries
        self._page_size = page_size
        self._sleep = sleep

    # ---- plumbing ---------------------------------------------------------

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http"):
            return path_or_url
        return f"{GRAPH_BASE}/{path_or_url.lstrip('/')}"

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._tokens.access_token()}",
            "Accept": "application/json",
            "Prefer": f'odata.maxpagesize={self._page_size}, outlook.timezone="UTC"',
        }
        if extra:
            headers.update(extra)
        return headers

    def request(self, method: str, path_or_url: str, *, params=None, json=None) -> httpx.Response:
        url = self._url(path_or_url)
        attempt = 0
        while True:
            response = self._client.request(method, url, params=params, json=json, headers=self._headers())
            if response.status_code in RETRY_STATUSES and attempt < self._max_retries:
                attempt += 1
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 30)
                self._sleep(delay)
                continue
            if response.status_code >= 400:
                try:
                    message = response.json().get("error", {}).get("message", response.text)
                except ValueError:
                    message = response.text
                raise GraphError(response.status_code, message, url)
            return response

    def get(self, path_or_url: str, params=None) -> dict[str, Any]:
        return self.request("GET", path_or_url, params=params).json()

    def post(self, path: str, json: dict) -> dict[str, Any]:
        response = self.request("POST", path, json=json)
        return response.json() if response.content else {}

    def patch(self, path: str, json: dict) -> dict[str, Any]:
        response = self.request("PATCH", path, json=json)
        return response.json() if response.content else {}

    def delete(self, path: str) -> None:
        self.request("DELETE", path)

    # ---- helpers ----------------------------------------------------------

    def me(self) -> dict[str, Any]:
        return self.get("me", params={"$select": "displayName,mail,userPrincipalName,id"})

    def iter_pages(self, path_or_url: str, params=None) -> Iterable[dict[str, Any]]:
        url: str | None = path_or_url
        first = True
        while url:
            page = self.get(url, params=params if first else None)
            first = False
            yield from page.get("value", [])
            url = page.get("@odata.nextLink")

    def delta(self, start_url: str) -> tuple[list[dict[str, Any]], str]:
        """Run one full round of a delta query. Returns (items, deltaLink)."""
        items: list[dict[str, Any]] = []
        url = start_url
        while True:
            page = self.get(url)
            items.extend(page.get("value", []))
            if "@odata.nextLink" in page:
                url = page["@odata.nextLink"]
                continue
            delta_link = page.get("@odata.deltaLink")
            if not delta_link:
                raise GraphError(500, "delta round ended without a deltaLink", url)
            return items, delta_link

    def close(self) -> None:
        self._client.close()
