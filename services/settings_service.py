"""Application service pour la gestion des paramètres utilisateur."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import os

from config.env_store import EnvStore
from config.settings import settings
from utils.insta_client import InstaClient, ClientError
from utils.logger import get_logger


logger = get_logger(__name__)


class SettingsError(RuntimeError):
	"""Erreur métier lors de la mise à jour des paramètres."""


@dataclass(slots=True)
class AccountPrivacy:
	username: str
	full_name: str | None
	is_private: bool
	is_verified: bool
	pk: int | None


class SettingsService:
	"""Orchestre les mises à jour des paramètres de configuration."""

	def __init__(
		self,
		*,
		env_store: EnvStore | None = None,
		insta_client_factory: Callable[[], InstaClient] | None = None,
	) -> None:
		self._env_store = env_store or EnvStore()
		self._insta_client_factory = insta_client_factory or InstaClient
		self._insta_client: InstaClient | None = None

	def _get_client(self) -> InstaClient:
		if self._insta_client is None:
			self._insta_client = self._insta_client_factory()
		return self._insta_client

	def settings_snapshot(self) -> Dict[str, object]:
		session_value = settings.instagram_sessionid or ""
		env_values = self._env_store.read()
		persisted_session = env_values.get("INSTAGRAM_SESSIONID")

		return {
			"target_accounts": settings.target_accounts,
			"auto_refresh_seconds": settings.dashboard_auto_refresh_seconds,
			"scrape_hour_utc": settings.scrape_hour_utc,
			"scrape_minute_utc": settings.scrape_minute_utc,
			"has_session_id": bool(session_value),
			"session_mask": self._mask_session(session_value),
			"session_persisted": bool(persisted_session),
		}

	def _mask_session(self, value: str) -> str:
		if not value:
			return ""
		if len(value) <= 8:
			return "*" * len(value)
		return f"{value[:4]}…{value[-4:]}"

	def set_session_id(self, value: str | None, *, persist: bool, clear_cached_session: bool = True) -> None:
		value = (value or "").strip()
		if value:
			session_value = value
			settings.instagram_sessionid = session_value
			os.environ["INSTAGRAM_SESSIONID"] = session_value
			if persist:
				self._env_store.set("INSTAGRAM_SESSIONID", session_value)
			else:
				# Ne persiste pas: supprimer l'entrée pour éviter les fuites.
				self._env_store.remove("INSTAGRAM_SESSIONID")
		else:
			settings.instagram_sessionid = None
			os.environ.pop("INSTAGRAM_SESSIONID", None)
			self._env_store.remove("INSTAGRAM_SESSIONID")

		if clear_cached_session:
			session_path = settings.instagram_session_path
			try:
				if session_path.exists():
					session_path.unlink()
					logger.info("Ancienne session Instagram supprimée (%s)", session_path)
			except OSError as exc:
				logger.warning("Impossible de supprimer la session Instagram: %s", exc)

	def set_auto_refresh_seconds(self, seconds: int) -> int:
		if seconds < 0:
			raise SettingsError("L'intervalle de rafraîchissement doit être positif.")
		if seconds and seconds < 30:
			raise SettingsError("Définissez au moins 30 secondes pour éviter le spam d'Instagram.")
		if seconds > 86400 * 2:
			raise SettingsError("La valeur maximale autorisée est de 172800 secondes.")

		settings.dashboard_auto_refresh_seconds = seconds
		self._env_store.set("AUTO_REFRESH_INTERVAL_SECONDS", str(seconds))
		return seconds

	def add_target_account(self, username: str) -> List[str]:
		clean_username = username.strip().lower()
		if not clean_username:
			raise SettingsError("Le nom d'utilisateur est obligatoire.")

		current = [account.strip().lower() for account in settings.target_accounts]
		if clean_username in current:
			raise SettingsError("Ce compte est déjà suivi.")

		settings.target_accounts.append(clean_username)
		self._persist_accounts()
		return settings.target_accounts

	def remove_target_account(self, username: str) -> List[str]:
		target = username.strip().lower()
		settings.target_accounts = [account for account in settings.target_accounts if account.lower() != target]
		self._persist_accounts()
		return settings.target_accounts

	def _persist_accounts(self) -> None:
		joined = ",".join(settings.target_accounts)
		self._env_store.set("TARGET_ACCOUNTS", joined)

	def check_account_privacy(self, username: str) -> AccountPrivacy:
		clean_username = username.strip()
		if not clean_username:
			raise SettingsError("Le nom d'utilisateur est obligatoire.")
		try:
			profile = self._get_client().get_user_profile(clean_username)
		except ClientError as exc:
			raise SettingsError(f"Impossible de récupérer les informations Instagram: {exc}") from exc
		except RuntimeError as exc:
			raise SettingsError(str(exc)) from exc

		return AccountPrivacy(
			username=profile.get("username", clean_username),
			full_name=profile.get("full_name") or None,
			is_private=bool(profile.get("is_private")),
			is_verified=bool(profile.get("is_verified")),
			pk=profile.get("pk"),
		)

	def send_follow_request(self, username: str) -> Dict[str, object]:
		try:
			result = self._get_client().send_follow_request(username.strip())
		except ClientError as exc:
			raise SettingsError(f"La demande de suivi a échoué: {exc}") from exc
		except RuntimeError as exc:
			raise SettingsError(str(exc)) from exc

		status = result.get("status") if isinstance(result, dict) else None
		return {
			"accepted": bool(result.get("friendship_status", {}).get("following")) if isinstance(result, dict) else False,
			"pending": bool(result.get("friendship_status", {}).get("outgoing_request")) if isinstance(result, dict) else False,
			"raw": result,
			"status": status,
		}

	def close(self) -> None:
		if self._insta_client is not None:
			try:
				self._insta_client.close()
			except Exception:  # pragma: no cover - fermeture best effort
				logger.debug("Fermeture du client Instagram ignorée")
			self._insta_client = None


settings_service = SettingsService()
