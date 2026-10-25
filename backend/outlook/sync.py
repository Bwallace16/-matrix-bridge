"""Pull from Graph with delta queries, keep the mirror honest, build the digest."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import quote

from .config import OutlookSettings
from .graph import GraphClient
from .models import MAIL_SELECT, Account, CalendarItem, DigestFlags, MailItem, OutlookDigest, PullResult
from .privacy import PrivacyFilter
from .state import StateStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutlookSync:
    def __init__(
        self,
        graph: GraphClient,
        store: StateStore,
        settings: OutlookSettings,
        privacy: PrivacyFilter | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ):
        self.graph = graph
        self.store = store
        self.settings = settings
        self.clock = clock
        self._privacy = privacy

    # ---- account + filter -------------------------------------------------

    def account(self) -> Account:
        state = self.store.load_state()
        if state.account.email:
            return state.account
        me = self.graph.me()
        account = Account(
            name=me.get("displayName") or "",
            email=(me.get("mail") or me.get("userPrincipalName") or "").lower(),
            id=me.get("id") or "",
        )
        state.account = account
        self.store.save_state(state)
        return account

    @property
    def privacy(self) -> PrivacyFilter:
        if self._privacy is None:
            self._privacy = PrivacyFilter(
                self.settings.internal_domains, self.settings.personal_keywords, self.account().email
            )
        return self._privacy

    # ---- pull -------------------------------------------------------------

    def _initial_calendar_url(self) -> str:
        now = self.clock()
        start = (now - timedelta(days=self.settings.calendar_lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (now + timedelta(days=self.settings.calendar_lookahead_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"me/calendarView/delta?startDateTime={start}&endDateTime={end}"

    def _initial_mail_url(self, folder: str) -> str:
        return f"me/mailFolders/{quote(folder)}/messages/delta?$select={MAIL_SELECT}"

    def pull(self) -> PullResult:
        privacy = self.privacy  # resolves the account first, so state below is current
        state = self.store.load_state()
        result = PullResult(pulled_at=self.clock(), first_pull=not state.calendar_delta_link)

        # Calendar
        events = self.store.load_events()
        raw, state.calendar_delta_link = self.graph.delta(state.calendar_delta_link or self._initial_calendar_url())
        parsed = [CalendarItem.from_graph(n) for n in raw]
        result.events_seen = len(parsed)
        kept, _ = privacy.filter_events(parsed)
        for item in kept:
            if item.removed:
                if events.pop(item.id, None) is not None:
                    result.events_removed += 1
            else:
                events[item.id] = item
                result.events_kept += 1
        # An event that used to pass the filter and now fails it (attendees dropped) leaves the mirror.
        for item in parsed:
            if not item.removed and item.id in events and item not in kept:
                events.pop(item.id)
        self.store.save_events(events)

        # Mail, one delta stream per folder
        messages = self.store.load_messages()
        for folder in self.settings.mail_folders:
            start = state.mail_delta_links.get(folder) or self._initial_mail_url(folder)
            raw, state.mail_delta_links[folder] = self.graph.delta(start)
            parsed_mail = [MailItem.from_graph(n, folder) for n in raw]
            result.messages_seen += len(parsed_mail)
            kept_mail, _ = privacy.filter_messages(parsed_mail)
            kept_ids = {m.id for m in kept_mail}
            for item in kept_mail:
                if item.removed:
                    if messages.pop(item.id, None) is not None:
                        result.messages_removed += 1
                else:
                    messages[item.id] = item
                    result.messages_kept += 1
            for item in parsed_mail:
                if not item.removed and item.id in messages and item.id not in kept_ids:
                    messages.pop(item.id)
        self.store.save_messages(messages)

        state.last_pull = result.pulled_at
        state.pull_count += 1
        self.store.save_state(state)
        return result

    # ---- digest -----------------------------------------------------------

    def digest(self, since: datetime, until: datetime | None = None) -> OutlookDigest:
        until = until or self.clock()
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        account = self.account()
        owner = account.email
        stale_cutoff = until - timedelta(days=self.settings.stale_after_days)

        mirror_events = list(self.store.load_events().values())
        floor = datetime.min.replace(tzinfo=timezone.utc)
        events = [
            e
            for e in mirror_events
            if (e.start and since <= e.start <= until) or (e.last_modified and since <= e.last_modified <= until)
        ]
        events.sort(key=lambda e: e.start or floor)
        upcoming = [e for e in mirror_events if e.start and e.start > until and not e.is_cancelled]
        upcoming.sort(key=lambda e: e.start or floor)

        all_messages = list(self.store.load_messages().values())
        messages = [m for m in all_messages if m.when and since <= m.when <= until]
        messages.sort(key=lambda m: m.when or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        # Flags: drafts untouched past the threshold; inbound external mail with no reply from me.
        stale_drafts = [m.id for m in all_messages if m.is_draft and m.last_modified and m.last_modified < stale_cutoff]
        stale_ids = set(stale_drafts)
        my_replies_by_conv: dict[str, datetime] = {}
        for m in all_messages:
            if m.sender.email == owner and m.when and not m.is_draft:
                prev = my_replies_by_conv.get(m.conversation_id)
                if prev is None or m.when > prev:
                    my_replies_by_conv[m.conversation_id] = m.when
        # One flag per conversation: the newest inbound message I have not answered.
        latest_unanswered: dict[str, MailItem] = {}
        for m in all_messages:
            if (
                m.folder == "inbox"
                and not m.is_draft
                and m.when
                and since <= m.when < stale_cutoff
                and m.sender.email != owner
                and self.privacy.is_external(m.sender.email)
                and my_replies_by_conv.get(m.conversation_id, floor) < m.when
            ):
                current = latest_unanswered.get(m.conversation_id)
                if current is None or (current.when or floor) < m.when:
                    latest_unanswered[m.conversation_id] = m
        unanswered = [m.id for m in sorted(latest_unanswered.values(), key=lambda m: m.when or floor, reverse=True)]

        # Every flagged message rides along, even one older than the window, so consumers can show it.
        present = {m.id for m in messages}
        for m in all_messages:
            if m.id in stale_ids and m.id not in present:
                messages.append(m)
                present.add(m.id)
        contacts = sorted(
            {e for ev in events + upcoming for e in ev.external_attendees}
            | {c for m in messages for c in m.counterparts}
        )

        return OutlookDigest(
            generated_at=self.clock(),
            since=since,
            until=until,
            account=account,
            events=events,
            upcoming=upcoming,
            messages=messages,
            flags=DigestFlags(stale_drafts=stale_drafts, unanswered=unanswered, contacts_seen=contacts),
            stats={
                "events": len(events),
                "upcoming": len(upcoming),
                "messages": len(messages),
                "stale_drafts": len(stale_drafts),
                "unanswered": len(unanswered),
                "contacts": len(contacts),
                "mirror_events": len(mirror_events),
                "mirror_messages": len(all_messages),
            },
        )

    def status(self) -> dict:
        state = self.store.load_state()
        return {
            "account": state.account.model_dump(),
            "last_pull": state.last_pull.isoformat() if state.last_pull else None,
            "pull_count": state.pull_count,
            "has_calendar_delta": bool(state.calendar_delta_link),
            "mail_folders": sorted(state.mail_delta_links),
            "mirror": {"events": len(self.store.load_events()), "messages": len(self.store.load_messages())},
            "subscriptions": {
                k: {"id": v.get("id"), "expires": v.get("expirationDateTime")} for k, v in state.subscriptions.items()
            },
        }
