"""The line nothing personal crosses. Runs before storage, before the digest, before any agent sees it."""

from __future__ import annotations

from .models import CalendarItem, MailItem


class PrivacyFilter:
    """Keep business items. Drop family, personal and internal-only noise.

    Rules, in order:
    1. A subject (or mail preview) that contains a personal keyword is dropped.
    2. A calendar event with no external attendee is dropped. Solo blocks and
       family events have none.
    3. A mail item with no external counterpart is dropped, unless it is a draft
       (stale drafts are something the owner wants flagged).
    """

    def __init__(self, internal_domains: list[str], personal_keywords: list[str], owner_email: str = ""):
        self._domains = {d.lower().lstrip("@") for d in internal_domains if d}
        self._keywords = [k.lower() for k in personal_keywords if k]
        self._owner = owner_email.lower()
        if self._owner and "@" in self._owner:
            self._domains.add(self._owner.split("@", 1)[1])

    # ---- predicates -------------------------------------------------------

    def is_internal(self, email: str) -> bool:
        email = (email or "").lower()
        if not email or email == self._owner:
            return True
        domain = email.split("@", 1)[-1]
        return domain in self._domains

    def is_external(self, email: str) -> bool:
        return bool(email) and not self.is_internal(email)

    def _personal(self, *texts: str) -> bool:
        blob = " ".join(t.lower() for t in texts if t)
        return any(k in blob for k in self._keywords)

    # ---- items ------------------------------------------------------------

    def keep_event(self, item: CalendarItem) -> bool:
        if item.removed:
            return True  # removals must propagate so the mirror forgets them
        if self._personal(item.subject):
            return False
        externals = sorted({a.email for a in item.attendees if self.is_external(a.email)})
        if self.is_external(item.organizer.email):
            externals = sorted(set(externals) | {item.organizer.email})
        item.external_attendees = externals
        return bool(externals)

    def keep_message(self, item: MailItem) -> bool:
        if item.removed:
            return True
        if self._personal(item.subject, item.preview):
            return False
        people = [item.sender.email] + [p.email for p in item.to] + [p.email for p in item.cc]
        item.counterparts = sorted({e for e in people if self.is_external(e)})
        if item.is_draft:
            return True
        return bool(item.counterparts)

    def filter_events(self, items: list[CalendarItem]) -> tuple[list[CalendarItem], int]:
        kept = [i for i in items if self.keep_event(i)]
        return kept, len(items) - len(kept)

    def filter_messages(self, items: list[MailItem]) -> tuple[list[MailItem], int]:
        kept = [i for i in items if self.keep_message(i)]
        return kept, len(items) - len(kept)
