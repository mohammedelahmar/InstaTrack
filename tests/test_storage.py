import os
from datetime import UTC, datetime, timedelta

os.environ["USE_MOCK_DB"] = "1"

from utils.storage import MongoStorage


def test_store_and_retrieve_snapshot():
	storage = MongoStorage()
	now = datetime.now(UTC)
	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 1, "username": "alice"}],
		collected_at=now,
	)

	snapshot = storage.latest_snapshot("demo", "followers")
	assert snapshot is not None
	assert snapshot["users"][0]["username"] == "alice"

import os
from datetime import UTC, datetime, timedelta

os.environ["USE_MOCK_DB"] = "1"

from utils.storage import MongoStorage


def test_store_and_retrieve_snapshot():
	storage = MongoStorage()
	now = datetime.now(UTC)
	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 1, "username": "alice"}],
		collected_at=now,
	)

	snapshot = storage.latest_snapshot("demo", "followers")
	assert snapshot is not None
	assert snapshot["users"][0]["username"] == "alice"


def test_changes_since_filters_by_time_and_account():
	storage = MongoStorage()
	detection_time = datetime.now(UTC)
	storage.store_changes(
		[
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": detection_time,
				"user": {"pk": 2, "username": "bob"},
			}
		]
	)

	recent = storage.changes_since(target_account="demo", since=detection_time - timedelta(days=1))
	assert len(recent) == 1
	assert recent[0]["user"]["username"] == "bob"


def test_changes_since_respects_limit():
	storage = MongoStorage()
	base_time = datetime.now(UTC)
	storage.store_changes(
		[
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time,
				"user": {"pk": 1, "username": "alice"},
			},
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time - timedelta(minutes=1),
				"user": {"pk": 2, "username": "bob"},
			},
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "removed",
				"detected_at": base_time - timedelta(minutes=2),
				"user": {"pk": 3, "username": "carol"},
			},
		]
	)

	results = storage.changes_since(target_account="demo", limit=2)
	assert len(results) == 2
	assert results[0]["user"]["username"] == "alice"
	assert results[1]["user"]["username"] == "bob"


def test_changes_since_accepts_end_bound():
	storage = MongoStorage()
	base_time = datetime.now(UTC)
	storage.store_changes(
		[
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time - timedelta(days=3),
				"user": {"pk": 1, "username": "old"},
			},
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time - timedelta(days=1),
				"user": {"pk": 2, "username": "recent"},
			},
		]
	)

	filtered = storage.changes_since(
		target_account="demo",
		since=base_time - timedelta(days=2),
		until=base_time,
	)
	assert len(filtered) == 1
	assert filtered[0]["user"]["username"] == "recent"


def test_snapshot_history_and_lookup_helpers():
	storage = MongoStorage()
	base_time = datetime(2025, 1, 1, 12, tzinfo=UTC)
	for offset in range(4):
		storage.store_snapshot(
			target_account="demo",
			list_type="followers",
			users=[{"pk": offset, "username": f"user{offset}"}],
			collected_at=base_time + timedelta(days=offset),
		)

	latest = storage.latest_snapshot("demo", "followers")
	assert latest is not None
	assert latest["users"][0]["username"] == "user3"

	before = storage.snapshot_at(
		target_account="demo",
		list_type="followers",
		moment=base_time + timedelta(days=1, hours=1),
	)
	assert before is not None
	assert before["users"][0]["username"] == "user1"

	after = storage.snapshot_at(
		target_account="demo",
		list_type="followers",
		moment=base_time - timedelta(days=1),
		direction="after",
	)
	assert after is not None
	assert after["users"][0]["username"] == "user0"

	history = storage.snapshot_history(
		target_account="demo",
		list_type="followers",
		limit=2,
	)
	assert len(history) == 2
	assert history[0]["users"][0]["username"] == "user3"
	assert history[1]["users"][0]["username"] == "user2"

	ranged = storage.snapshot_history(
		target_account="demo",
		list_type="followers",
		start=base_time + timedelta(days=1),
		end=base_time + timedelta(days=2),
	)
	assert len(ranged) == 2
