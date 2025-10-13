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
