"""HTTP surface: /api/outlook/*"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .auth import AuthRequired, MsalTokenProvider
from .config import OutlookSettings
from .graph import GraphClient, GraphError
from .state import StateStore
from .sync import OutlookSync
from .webhooks import ClientStateMismatch, SubscriptionManager, parse_notifications

log = logging.getLogger("matrix_bridge.outlook")
router = APIRouter(prefix="/api/outlook", tags=["outlook"])


class Runtime:
    """Everything the routes need, built once. Swap it out in tests."""

    def __init__(self, settings: OutlookSettings, sync: OutlookSync | None = None):
        self.settings = settings
        self.store = StateStore(settings.state_dir)
        self._sync = sync

    @property
    def sync(self) -> OutlookSync:
        if self._sync is None:
            if not self.settings.configured:
                raise AuthRequired("OUTLOOK_CLIENT_ID is not set")
            tokens = MsalTokenProvider(self.settings)
            graph = GraphClient(tokens, page_size=self.settings.page_size)
            self._sync = OutlookSync(graph, self.store, self.settings)
        return self._sync

    def subscriptions(self) -> SubscriptionManager:
        return SubscriptionManager(
            self.sync.graph, self.store, self.settings.notification_url, self.settings.client_state
        )


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime(OutlookSettings())
    return _runtime


def set_runtime(runtime: Runtime | None) -> None:
    global _runtime
    _runtime = runtime


def _auth_error(err: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "outlook_not_ready", "detail": str(err)})


@router.get("/status")
def status() -> dict[str, Any]:
    rt = get_runtime()
    base = {
        "configured": rt.settings.configured,
        "tenant": rt.settings.tenant_id,
        "scopes": rt.settings.scopes,
        "mail_folders": rt.settings.mail_folders,
        "webhooks": bool(rt.settings.notification_url),
    }
    try:
        base.update(rt.sync.status())
        base["signed_in"] = True
    except AuthRequired as err:
        base["signed_in"] = False
        base["detail"] = str(err)
    return base


@router.post("/pull")
def pull():
    rt = get_runtime()
    try:
        return rt.sync.pull().model_dump(mode="json")
    except AuthRequired as err:
        return _auth_error(err)
    except GraphError as err:
        raise HTTPException(status_code=502, detail=str(err))


@router.get("/digest")
def digest(
    since: datetime | None = Query(default=None, description="ISO datetime. Default: 7 days ago."),
    until: datetime | None = Query(default=None),
    refresh: bool = Query(default=False, description="Pull from Graph before building the digest."),
):
    rt = get_runtime()
    since = since or datetime.now(timezone.utc) - timedelta(days=7)
    try:
        if refresh:
            rt.sync.pull()
        return rt.sync.digest(since, until).model_dump(mode="json", by_alias=True)
    except AuthRequired as err:
        return _auth_error(err)
    except GraphError as err:
        raise HTTPException(status_code=502, detail=str(err))


@router.post("/notifications")
async def notifications(request: Request, background: BackgroundTasks):
    # Step 1 of the Graph handshake: echo the validation token as text/plain.
    token = request.query_params.get("validationToken")
    if token:
        return PlainTextResponse(token, status_code=200)

    rt = get_runtime()
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(status_code=202, content={"accepted": 0})
    try:
        notes = parse_notifications(body, rt.settings.client_state)
    except ClientStateMismatch as err:
        log.warning("Dropped notification with bad clientState: %s", err)
        return JSONResponse(status_code=202, content={"accepted": 0})
    if notes:
        background.add_task(_safe_pull, rt)
    # Always 202 fast. Graph retries anything slower than 3 seconds.
    return JSONResponse(status_code=202, content={"accepted": len(notes)})


def _safe_pull(rt: Runtime) -> None:
    try:
        result = rt.sync.pull()
        log.info("Webhook pull: %s", result.model_dump())
    except Exception as err:  # noqa: BLE001  background task, log and move on
        log.exception("Webhook-triggered pull failed: %s", err)


@router.post("/subscriptions")
def subscribe():
    rt = get_runtime()
    try:
        return rt.subscriptions().ensure()
    except AuthRequired as err:
        return _auth_error(err)
    except (GraphError, ValueError) as err:
        raise HTTPException(status_code=502, detail=str(err))


@router.delete("/subscriptions")
def unsubscribe():
    rt = get_runtime()
    try:
        return {"removed": rt.subscriptions().remove_all()}
    except AuthRequired as err:
        return _auth_error(err)
    except GraphError as err:
        raise HTTPException(status_code=502, detail=str(err))
