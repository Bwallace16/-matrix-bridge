"""python -m outlook <command>

  auth                 sign in once with the device code flow
  status               what the mirror knows
  pull                 run a delta round against Graph
  digest               write the digest JSON (default: last 7 days, stdout)
  subscribe            create or renew Graph webhooks
  unsubscribe          delete them
  reset                forget delta links and the mirror (token stays)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .auth import AuthRequired, MsalTokenProvider
from .config import OutlookSettings
from .graph import GraphClient, GraphError
from .state import StateStore
from .sync import OutlookSync
from .webhooks import SubscriptionManager


def _build(settings: OutlookSettings) -> OutlookSync:
    tokens = MsalTokenProvider(settings)
    graph = GraphClient(tokens, page_size=settings.page_size)
    return OutlookSync(graph, StateStore(settings.state_dir), settings)


def _parse_dt(text: str | None, default: datetime) -> datetime:
    if not text:
        return default
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m outlook",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("auth")
    sub.add_parser("status")
    sub.add_parser("pull")
    d = sub.add_parser("digest")
    d.add_argument("--since", help="ISO date or datetime. Default: 7 days ago.")
    d.add_argument("--until", help="ISO date or datetime. Default: now.")
    d.add_argument("--out", help="File path. Default: stdout.")
    d.add_argument("--no-pull", action="store_true", help="Build from the mirror without hitting Graph.")
    sub.add_parser("subscribe")
    sub.add_parser("unsubscribe")
    sub.add_parser("reset")
    args = parser.parse_args(argv)

    settings = OutlookSettings()
    try:
        if args.command == "auth":
            who = MsalTokenProvider(settings).login_device_flow()
            print(json.dumps(who, indent=2))
            return 0
        if args.command == "reset":
            StateStore(settings.state_dir).reset()
            print("Mirror and delta links cleared.")
            return 0

        sync = _build(settings)
        if args.command == "status":
            print(json.dumps(sync.status(), indent=2, default=str))
        elif args.command == "pull":
            print(json.dumps(sync.pull().model_dump(mode="json"), indent=2))
        elif args.command == "digest":
            if not args.no_pull:
                sync.pull()
            now = datetime.now(timezone.utc)
            digest = sync.digest(_parse_dt(args.since, now - timedelta(days=7)), _parse_dt(args.until, now))
            text = digest.model_dump_json(indent=2, by_alias=True)
            if args.out:
                Path(args.out).write_text(text)
                print(f"Wrote {args.out}: {digest.stats}", file=sys.stderr)
            else:
                print(text)
        elif args.command == "subscribe":
            mgr = SubscriptionManager(sync.graph, sync.store, settings.notification_url, settings.client_state)
            print(json.dumps(mgr.ensure(), indent=2, default=str))
        elif args.command == "unsubscribe":
            mgr = SubscriptionManager(sync.graph, sync.store, settings.notification_url, settings.client_state)
            print(json.dumps({"removed": mgr.remove_all()}))
        return 0
    except AuthRequired as err:
        print(f"Not signed in: {err}", file=sys.stderr)
        return 2
    except GraphError as err:
        print(str(err), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
