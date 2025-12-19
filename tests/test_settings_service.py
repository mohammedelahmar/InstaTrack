import os
from pathlib import Path

import pytest

from config.env_store import EnvStore
from config.settings import settings
from services.settings_service import SettingsError, SettingsService


class DummyInstaClient:
	def __init__(self, *, profile=None, follow_result=None):
		self._profile = profile or {
			"username": "demo",
			"full_name": "Demo Account",
			"is_private": False,
			"is_verified": False,
			"pk": 123,
		}
		self._follow_result = follow_result or {
			"status": "ok",
			"friendship_status": {
				"following": True,
				"outgoing_request": False,
			},
		}

	def get_user_profile(self, username: str):
		profile = dict(self._profile)
		profile.setdefault("username", username)
		profile.setdefault("pk", 999)
		return profile

	def send_follow_request(self, username: str):
		return dict(self._follow_result)

	def close(self):
		return None


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
	env_path = tmp_path / "test.env"
	env_store = EnvStore(env_path)

	# Back up mutable settings fields
	original_accounts = list(settings.target_accounts)
	original_session = settings.instagram_sessionid
	original_auto = settings.dashboard_auto_refresh_seconds
	original_session_path: Path = settings.instagram_session_path

	settings.target_accounts = []
	settings.instagram_sessionid = None
	settings.dashboard_auto_refresh_seconds = 0
	settings.instagram_session_path = tmp_path / "insta_session.json"

	backup_env = {
		"TARGET_ACCOUNTS": os.environ.get("TARGET_ACCOUNTS"),
		"INSTAGRAM_SESSIONID": os.environ.get("INSTAGRAM_SESSIONID"),
		"AUTO_REFRESH_INTERVAL_SECONDS": os.environ.get("AUTO_REFRESH_INTERVAL_SECONDS"),
	}

	yield env_store

	# Restore globals
	settings.target_accounts = original_accounts
	settings.instagram_sessionid = original_session
	settings.dashboard_auto_refresh_seconds = original_auto
	settings.instagram_session_path = original_session_path

	for key, value in backup_env.items():
		if value is None:
			os.environ.pop(key, None)
		else:
			os.environ[key] = value


def test_add_and_remove_target_account_updates_env(temp_env):
	service = SettingsService(env_store=temp_env)

	updated = service.add_target_account("nouveau_compte")
	assert "nouveau_compte" in updated
	assert temp_env.read()["TARGET_ACCOUNTS"] == "nouveau_compte"

	remaining = service.remove_target_account("nouveau_compte")
	assert "nouveau_compte" not in remaining
	assert temp_env.read().get("TARGET_ACCOUNTS", "") == ""


def test_set_session_id_persist_and_clear(temp_env, tmp_path):
	service = SettingsService(env_store=temp_env)
	fake_session = "1234567890abcdef"
	settings.instagram_session_path.write_text("cached")

	service.set_session_id(fake_session, persist=True)
	env_values = temp_env.read()
	assert env_values["INSTAGRAM_SESSIONID"] == fake_session
	assert settings.instagram_sessionid == fake_session

	service.set_session_id(None, persist=False)
	env_values = temp_env.read()
	assert "INSTAGRAM_SESSIONID" not in env_values
	assert settings.instagram_sessionid is None


def test_auto_refresh_validation(temp_env):
	service = SettingsService(env_store=temp_env)

	with pytest.raises(SettingsError):
		service.set_auto_refresh_seconds(-1)

	with pytest.raises(SettingsError):
		service.set_auto_refresh_seconds(10)  # en dessous du seuil de 30 s

	service.set_auto_refresh_seconds(120)
	assert settings.dashboard_auto_refresh_seconds == 120
	assert temp_env.read()["AUTO_REFRESH_INTERVAL_SECONDS"] == "120"


def test_check_account_privacy_uses_client(temp_env):
	dummy_client = DummyInstaClient(profile={
		"username": "privé",
		"full_name": "Compte Privé",
		"is_private": True,
		"is_verified": True,
		"pk": 555,
	})
	service = SettingsService(env_store=temp_env, insta_client_factory=lambda: dummy_client)

	privacy = service.check_account_privacy("prive")
	assert privacy.is_private is True
	assert privacy.full_name == "Compte Privé"
	assert privacy.pk == 555


def test_send_follow_request_returns_payload(temp_env):
	dummy_client = DummyInstaClient(follow_result={
		"status": "ok",
		"friendship_status": {
			"following": False,
			"outgoing_request": True,
		},
	})
	service = SettingsService(env_store=temp_env, insta_client_factory=lambda: dummy_client)

	result = service.send_follow_request("nouveau")
	assert result["pending"] is True
	assert result["accepted"] is False