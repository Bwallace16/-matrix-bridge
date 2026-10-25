from datetime import timedelta

from conftest import NOW, OWNER, event, mail


def test_first_pull_uses_window_then_delta_links(sync, fake_graph):
    fake_graph.queue("calendar", [event("e1", "Intro", NOW - timedelta(days=1), ["a@acme.io"])])
    result = sync.pull()
    assert result.first_pull
    assert result.events_kept == 1
    first_calendar_call = next(u for m, u in fake_graph.calls if "calendarView" in u)
    assert "startDateTime=2026-09-25" in first_calendar_call and "endDateTime=2026-11-08" in first_calendar_call

    state = sync.store.load_state()
    assert "$deltatoken=1-0" in state.calendar_delta_link
    assert set(state.mail_delta_links) == {"inbox", "sentitems", "drafts"}

    fake_graph.calls.clear()
    fake_graph.queue("calendar", [])
    second = sync.pull()
    assert not second.first_pull
    calendar_calls = [u for m, u in fake_graph.calls if "calendarView" in u]
    assert calendar_calls == [state.calendar_delta_link]


def test_paging_collects_every_item(sync, fake_graph):
    fake_graph.queue(
        "calendar", [event(f"e{i}", f"Call {i}", NOW - timedelta(days=i), ["x@acme.io"]) for i in range(5)]
    )
    result = sync.pull()
    assert result.events_seen == 5 and result.events_kept == 5
    assert len(sync.store.load_events()) == 5


def test_filter_applies_and_removals_clean_the_mirror(sync, fake_graph):
    fake_graph.queue(
        "calendar",
        [
            event("keep", "Client sync", NOW, ["c@acme.io"]),
            event("solo", "Focus time", NOW, []),
            event("fam", "Soccer practice", NOW, ["coach@club.org"]),
        ],
    )
    sync.pull()
    assert set(sync.store.load_events()) == {"keep"}

    fake_graph.queue("calendar", [{"id": "keep", "@removed": {"reason": "deleted"}}])
    result = sync.pull()
    assert result.events_removed == 1
    assert sync.store.load_events() == {}


def test_event_that_loses_its_externals_leaves_the_mirror(sync, fake_graph):
    fake_graph.queue("calendar", [event("e1", "Review", NOW, ["c@acme.io"])])
    sync.pull()
    fake_graph.queue("calendar", [event("e1", "Review", NOW, [])])
    sync.pull()
    assert sync.store.load_events() == {}


def test_throttle_is_retried(sync, fake_graph):
    fake_graph.throttle_once.add("calendar")
    fake_graph.queue("calendar", [event("e1", "Retry me", NOW, ["c@acme.io"])])
    assert sync.pull().events_kept == 1


def test_digest_windows_flags_and_contacts(sync, fake_graph):
    fake_graph.queue(
        "calendar",
        [
            event("in", "Kickoff", NOW - timedelta(days=2), ["pm@acme.io"]),
            event("old", "Last month", NOW - timedelta(days=20), ["pm@acme.io"]),
            event("next", "Follow-up", NOW + timedelta(days=3), ["cto@acme.io"]),
        ],
    )
    fake_graph.queue(
        "inbox",
        [
            mail("ask", "Can you send the deck?", "pm@acme.io", [OWNER], NOW - timedelta(days=5), conversation="deck"),
            mail(
                "ask2",
                "Re: Can you send the deck?",
                "pm@acme.io",
                [OWNER],
                NOW - timedelta(days=4),
                conversation="deck",
            ),
            mail("answered", "Pricing", "cfo@acme.io", [OWNER], NOW - timedelta(days=5), conversation="price"),
            mail("fresh", "Quick q", "new@startup.co", [OWNER], NOW - timedelta(hours=5), conversation="q"),
        ],
    )
    reply = mail("reply", "Re: Pricing", OWNER, ["cfo@acme.io"], NOW - timedelta(days=4), conversation="price")
    fake_graph.queue("sentitems", [reply])
    fake_graph.queue(
        "drafts",
        [
            mail("stale", "Intro", OWNER, ["pm@acme.io"], NOW - timedelta(days=9), is_draft=True),
            mail("recent", "Thanks", OWNER, ["pm@acme.io"], NOW - timedelta(hours=2), is_draft=True),
        ],
    )
    sync.pull()
    digest = sync.digest(NOW - timedelta(days=7))

    assert [e.id for e in digest.events] == ["in"]
    assert [e.id for e in digest.upcoming] == ["next"]
    assert {m.id for m in digest.messages} == {"ask", "ask2", "answered", "fresh", "reply", "recent", "stale"}
    assert digest.flags.unanswered == ["ask2"]
    assert digest.flags.stale_drafts == ["stale"]
    assert digest.flags.contacts_seen == ["cfo@acme.io", "cto@acme.io", "new@startup.co", "pm@acme.io"]
    assert digest.account.email == OWNER
    assert digest.stats["mirror_events"] == 3 and digest.stats["upcoming"] == 1

    payload = digest.model_dump(mode="json", by_alias=True)
    assert payload["schema"] == "matrix-bridge.outlook-digest/1"
    assert payload["events"][0]["external_attendees"] == ["pm@acme.io"]


def test_status_reports_mirror(sync, fake_graph):
    fake_graph.queue("calendar", [event("e1", "Call", NOW, ["c@acme.io"])])
    sync.pull()
    status = sync.status()
    assert status["pull_count"] == 1
    assert status["mirror"] == {"events": 1, "messages": 0}
    assert status["account"]["email"] == OWNER
