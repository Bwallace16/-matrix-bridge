from datetime import timedelta

from conftest import NOW, OWNER, event, mail
from outlook.models import CalendarItem, MailItem


def test_internal_and_owner_are_not_external(privacy):
    assert privacy.is_internal(OWNER)
    assert privacy.is_internal("colleague@example.com")
    assert privacy.is_internal("Colleague@EXAMPLE.com")
    assert privacy.is_external("client@acme.io")
    assert not privacy.is_external("")


def test_event_without_external_attendee_is_dropped(privacy):
    solo = CalendarItem.from_graph(event("e1", "Deep work", NOW, []))
    internal = CalendarItem.from_graph(event("e2", "Standup", NOW, ["colleague@example.com"]))
    assert not privacy.keep_event(solo)
    assert not privacy.keep_event(internal)


def test_event_with_external_attendee_is_kept_and_annotated(privacy):
    item = CalendarItem.from_graph(event("e3", "Discovery call", NOW, ["client@acme.io", "colleague@example.com"]))
    assert privacy.keep_event(item)
    assert item.external_attendees == ["client@acme.io"]


def test_external_organizer_counts(privacy):
    item = CalendarItem.from_graph(event("e4", "Their invite", NOW, [OWNER], organizer="host@partner.com"))
    assert privacy.keep_event(item)
    assert item.external_attendees == ["host@partner.com"]


def test_personal_keyword_drops_event_even_with_externals(privacy):
    item = CalendarItem.from_graph(event("e5", "Kids soccer with coach", NOW, ["coach@club.org"]))
    assert not privacy.keep_event(item)


def test_removed_items_always_pass_so_mirror_forgets_them(privacy):
    assert privacy.keep_event(CalendarItem(id="gone", removed=True))
    assert privacy.keep_message(MailItem(id="gone", removed=True))


def test_mail_counterparts_and_internal_only_drop(privacy):
    external = MailItem.from_graph(mail("m1", "Proposal", "client@acme.io", [OWNER], NOW), "inbox")
    internal = MailItem.from_graph(mail("m2", "Lunch?", "colleague@example.com", [OWNER], NOW), "inbox")
    assert privacy.keep_message(external)
    assert external.counterparts == ["client@acme.io"]
    assert not privacy.keep_message(internal)


def test_mail_preview_keyword_drops(privacy):
    item = MailItem.from_graph(
        mail("m3", "Reminder", "office@clinic.com", [OWNER], NOW, preview="Dentist appt"), "inbox"
    )
    assert not privacy.keep_message(item)


def test_drafts_survive_without_counterparts(privacy):
    draft = MailItem.from_graph(mail("d1", "", OWNER, [], NOW - timedelta(days=5), is_draft=True), "drafts")
    assert privacy.keep_message(draft)
