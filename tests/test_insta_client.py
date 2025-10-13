import os
from datetime import UTC, datetime

os.environ["USE_MOCK_DB"] = "1"

from config.settings import settings
from services.tracker_service import TrackerService
from utils.storage import MongoStorage


class DummyClient:
	def __init__(self) -> None:
		self.calls = 0

	def fetch_relationships(self, username: str):
		self.calls += 1
		followers = [
			{"pk": 1, "username": "alice", "full_name": "Alice"},
			{"pk": 2, "username": "bob", "full_name": "Bob"},
		]
		following = [
			{"pk": 3, "username": "carol", "full_name": "Carol"},
		]
		return followers, following


def test_tracker_service_stores_snapshots_and_changes():
	storage = MongoStorage()
	client = DummyClient()
	settings.target_accounts = ["demo"]

	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 1, "username": "alice", "full_name": "Alice"}],
		collected_at=datetime.now(UTC),
	)

	service = TrackerService(client=client, storage=storage)
	summaries = service.run_once()

	assert summaries[0]["followers_added"] == 1
	assert summaries[0]["followers_removed"] == 0
	assert client.calls == 1

	changes = storage.changes_since(target_account="demo")
	assert any(change["user"]["username"] == "bob" for change in changes)
