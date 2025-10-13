from datetime import UTC, datetime

from utils import comparer


def test_diff_users_detects_added_and_removed():
	previous = [
		{"pk": 1, "username": "alice", "full_name": "Alice"},
		{"pk": 2, "username": "bob", "full_name": "Bob"},
	]
	current = [
		{"pk": 2, "username": "bob", "full_name": "Bob"},
		{"pk": 3, "username": "carol", "full_name": "Carol"},
	]

	added, removed = comparer.diff_users(previous, current)

	assert added == [{"pk": 3, "username": "carol", "full_name": "Carol"}]
	assert removed == [{"pk": 1, "username": "alice", "full_name": "Alice"}]


def test_build_change_events_structure():
	added = [{"pk": 4, "username": "dan", "full_name": "Dan"}]
	removed = [{"pk": 5, "username": "erin", "full_name": "Erin"}]

	events = comparer.build_change_events(
		target_account="example",
		list_type="followers",
		added=added,
		removed=removed,
		detected_at=datetime.now(UTC),
	)

	assert len(events) == 2
	assert {event["change_type"] for event in events} == {"added", "removed"}
