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
