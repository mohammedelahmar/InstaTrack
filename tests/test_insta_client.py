import os
from datetime import UTC, datetime

import pytest

os.environ["USE_MOCK_DB"] = "1"

from config.settings import settings
from services.tracker_service import TrackerService
from utils import insta_client
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


class _SessionFailureClient:
	def __init__(self, exc: Exception) -> None:
		self.delay_range = (0, 0)
		self._exc = exc

	def login_by_sessionid(self, _session_id: str) -> None:
		raise self._exc

	def login(self, *_args, **_kwargs) -> None:
		"""Credentials-based login placeholder."""

	def dump_settings(self, *_args, **_kwargs) -> None:
		"""Avoid writing session files during tests."""

	def logout(self) -> None:  # pragma: no cover - defensive
		pass


def test_instaclient_sessionid_failure_requires_new_cookie(monkeypatch):
	original_session = settings.instagram_sessionid
	original_username = settings.instagram_username
	original_password = settings.instagram_password
	client_error = KeyError("data")

	try:
		settings.instagram_sessionid = "invalid"
		settings.instagram_username = None
		settings.instagram_password = None

		fake_client = _SessionFailureClient(client_error)
		monkeypatch.setattr(insta_client, "Client", lambda: fake_client)
		monkeypatch.setattr(insta_client.InstaClient, "_load_session", lambda self: False)

		client = insta_client.InstaClient()

		with pytest.raises(insta_client.ClientLoginRequired):
			client.login()
	finally:
		settings.instagram_sessionid = original_session
		settings.instagram_username = original_username
		settings.instagram_password = original_password


def test_instaclient_sessionid_failure_falls_back_to_credentials(monkeypatch):
	original_session = settings.instagram_sessionid
	original_username = settings.instagram_username
	original_password = settings.instagram_password

	class _FallbackClient(_SessionFailureClient):
		def __init__(self) -> None:
			super().__init__(insta_client.ClientError("boom"))
			self.login_calls = 0

		def login(self, username: str, password: str) -> None:
			self.login_calls += 1
			self.last_credentials = (username, password)

	try:
		settings.instagram_sessionid = "expired"
		settings.instagram_username = "demo_user"
		settings.instagram_password = "demo_pass"

		fake_client = _FallbackClient()
		monkeypatch.setattr(insta_client, "Client", lambda: fake_client)
		monkeypatch.setattr(insta_client.InstaClient, "_load_session", lambda self: False)

		client = insta_client.InstaClient()
		client.login()

		assert fake_client.login_calls == 1
		assert client._logged_in is True
		assert fake_client.last_credentials == ("demo_user", "demo_pass")
	finally:
		settings.instagram_sessionid = original_session
		settings.instagram_username = original_username
		settings.instagram_password = original_password
