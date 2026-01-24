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


def test_instaclient_sessionid_keyerror_falls_back_to_cache(monkeypatch, tmp_path):
	original_session = settings.instagram_sessionid
	original_session_path = settings.instagram_session_path
	settings.instagram_sessionid = "valid_cookie"
	settings.instagram_session_path = tmp_path / "insta_session.json"

	class _KeyErrorClient(_SessionFailureClient):
		def __init__(self) -> None:
			super().__init__(KeyError("data"))

		def get_timeline_feed(self):
			return True

		def load_settings(self, *_args, **_kwargs):
			return True

		def dump_settings(self, *_args, **_kwargs):
			return None

	client_instance = _KeyErrorClient()

	state = {"calls": 0}

	def _fake_load_session(self):
		state["calls"] += 1
		# First call: pretend cache not yet loaded (before sessionid path).
		if state["calls"] == 1:
			return False
		# Second call (after sessionid failure): succeed and mark logged in.
		self._logged_in = True
		return True

	monkeypatch.setattr(insta_client, "Client", lambda: client_instance)
	monkeypatch.setattr(insta_client.InstaClient, "_load_session", _fake_load_session)

	try:
		client = insta_client.InstaClient()
		client.login()
		assert client._logged_in is True
	except Exception as exc:  # pragma: no cover - defensive guard
		raise
	finally:
		settings.instagram_sessionid = original_session
		settings.instagram_session_path = original_session_path


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


def test_follow_request_retries_after_login_required(monkeypatch, tmp_path):
	original_session = settings.instagram_sessionid
	original_session_path = settings.instagram_session_path
	settings.instagram_sessionid = "valid"
	settings.instagram_session_path = tmp_path / "insta_session.json"

	counter = {"calls": 0}

	class _FollowClient:
		def __init__(self) -> None:
			self.delay_range = (0, 0)

		def login_by_sessionid(self, _session_id: str) -> None:
			return None

		def dump_settings(self, *_args, **_kwargs) -> None:
			return None

		def user_id_from_username(self, _username: str) -> int:
			return 123

		def friendships_create(self, _user_id: int):
			counter["calls"] += 1
			if counter["calls"] == 1:
				raise insta_client.ClientLoginRequired("login_required")
			return {"status": "ok", "friendship_status": {"outgoing_request": True}}

		def logout(self):  # pragma: no cover - defensive
			return None

	factory_iter = iter([_FollowClient(), _FollowClient()])
	monkeypatch.setattr(insta_client, "Client", lambda: next(factory_iter))
	monkeypatch.setattr(insta_client.InstaClient, "_load_session", lambda self: False)

	try:
		client = insta_client.InstaClient()
		result = client.send_follow_request("demo")
		assert result["status"] == "ok"
		assert counter["calls"] == 2
	finally:
		settings.instagram_sessionid = original_session
		settings.instagram_session_path = original_session_path
