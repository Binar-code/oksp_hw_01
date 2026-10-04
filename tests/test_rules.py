from datetime import datetime, timedelta, timezone

from app.rules import can_change_status, reaction

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_reply_on_time():
    reply = START + timedelta(minutes=60)
    assert reaction(START, reply, 60, reply) == {'reaction_minutes': 60, 'overdue': False}


def test_late_reply():
    reply = START + timedelta(minutes=90)
    assert reaction(START, reply, 60, reply) == {'reaction_minutes': 90, 'overdue': True}


def test_no_reply():
    now = START + timedelta(minutes=90)
    assert reaction(START, None, 60, now) == {'reaction_minutes': None, 'overdue': True}


def test_status_transitions():
    assert can_change_status('new', 'in_progress')
    assert can_change_status('in_progress', 'closed')
    assert not can_change_status('new', 'closed')
