"""Wrapper around instagrapi for follower/following snapshots."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Tuple

try:  # pragma: no cover - import guarded for test environments
	from instagrapi import Client
	from instagrapi.exceptions import (
		ChallengeRequired,
		ClientError,
		ClientLoginRequired,
		PleaseWaitFewMinutes,
		TwoFactorRequired,
	)
except ImportError:  # pragma: no cover - fallback when library missing
	Client = None  # type: ignore

	class ClientError(Exception):
		"""Fallback exception when instagrapi n'est pas installé."""

	class ClientLoginRequired(ClientError):
		"""Raised when Instagram requires a fresh login."""

	class ChallengeRequired(ClientError):
		"""Raised when Instagram requests additional verification."""

	class TwoFactorRequired(ClientError):
		"""Raised when 2FA is required for login."""

	class PleaseWaitFewMinutes(ClientError):
		"""Raised when Instagram rate limits login attempts."""


from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)


UserMap = Dict[int, Dict[str, str]]


def _simplify_users(users: UserMap) -> List[Dict[str, str]]:
	simplified: List[Dict[str, str]] = []
	for user_id, info in users.items():
		data: Dict[str, str] = {}
		if isinstance(info, dict):
			data = info
		else:
			if hasattr(info, "model_dump"):
				try:
					data = info.model_dump()
				except Exception:  # pragma: no cover - fallback for unexpected behaviour
					data = {}
			elif hasattr(info, "dict"):
				try:
					data = info.dict()
				except Exception:  # pragma: no cover - fallback for unexpected behaviour
					data = {}
			if not data:
				data = {
					"pk": getattr(info, "pk", user_id),
					"username": getattr(info, "username", ""),
					"full_name": getattr(info, "full_name", ""),
				}
		simplified.append(
			{
				"pk": user_id,
				"username": data.get("username", ""),
				"full_name": data.get("full_name", ""),
			}
		)
	return simplified


class InstaClient:
	"""High-level client with login persistence and retry logic."""

	def __init__(self) -> None:
		if Client is None:
			raise RuntimeError(
				"instagrapi n'est pas installé. Ajoutez-le à votre environnement ou utilisez un client factice."
			)
		self._client = Client()
		self._client.delay_range = (settings.min_request_delay, settings.max_request_delay)
		self._session_path = Path(settings.instagram_session_path)
		self._logged_in = False

	def _load_session(self) -> bool:
		if settings.instagram_disable_session:
			logger.info("Instagram session caching disabled; starting fresh login")
			return False
		if not self._session_path.exists():
			return False
		try:
			self._client.load_settings(self._session_path.read_text())
			self._client.get_timeline_feed()
			self._logged_in = True
			logger.info("Loaded cached Instagram session from %s", self._session_path)
			return True
		except ClientLoginRequired:
			logger.info("Cached Instagram session expired; performing fresh login")
			return False
		except ClientError as exc:
			logger.warning("Cached Instagram session invalid: %s", exc)
			return False
		except Exception as exc:  # pragma: no cover - defensive path
			logger.warning("Failed to load cached Instagram session: %s", exc)
			return False

	def _dump_session(self) -> None:
		if settings.instagram_disable_session:
			return
		try:
			self._client.dump_settings(self._session_path)
			logger.info("Stored new Instagram session in %s", self._session_path)
		except Exception as exc:  # pragma: no cover - defensive path
			logger.warning("Unable to persist Instagram session: %s", exc)

	def _handle_challenge(self, error: ChallengeRequired) -> bool:
		challenge = getattr(error, "challenge", None)
		api_path = "unknown"
		if isinstance(challenge, dict):
			api_path = challenge.get("api_path", api_path)
		elif challenge is not None:
			api_path = getattr(challenge, "api_path", api_path)
		if not challenge:
			logger.error(
				"Instagram requested additional verification but no challenge details were provided; please verify manually."
			)
			return False
		try:
			logger.warning(
				"Instagram requested additional verification (endpoint: %s); attempting automated resolution",
				api_path,
			)
			result = self._client.challenge_resolve(challenge)
			if isinstance(result, dict) and result.get("status") == "ok":
				return True
			logger.info(
				"Instagram challenge resolution returned %s; manual intervention may still be required",
				result,
			)
		except Exception as exc:  # pragma: no cover - best effort
			logger.error("Automatic Instagram challenge resolution failed: %s", exc)
		return False

	def _handle_two_factor(self, error: TwoFactorRequired) -> bool:
		info = getattr(error, "two_factor_info", {}) or {}
		logger.error(
			"Instagram two-factor authentication required (%s); provide INSTAGRAM_SESSIONID or complete verification manually.",
			info.get("obfuscated_phone_number", "unknown"),
		)
		return False

	def _handle_rate_limit(self, exc: PleaseWaitFewMinutes) -> None:
		delay = getattr(exc, "retry_after", settings.retry_backoff_seconds)
		logger.warning(
			"Instagram asked to wait before retrying login (retry after %.0f seconds)",
			delay,
		)
		time.sleep(delay)

	def _login_with_credentials(self) -> None:
		last_error: Exception | None = None
		for attempt in range(1, settings.max_retries + 1):
			try:
				self._client.login(settings.instagram_username, settings.instagram_password)
				self._logged_in = True
				logger.info("Authenticated with Instagram as %s", settings.instagram_username)
				self._dump_session()
				return
			except ChallengeRequired as exc:
				last_error = exc
				if self._handle_challenge(exc):
					logger.info("Instagram challenge resolved; retrying login")
					time.sleep(settings.retry_backoff_seconds)
					continue
				logger.error(
					"Instagram challenge couldn't be solved automatically. Complete verification via the Instagram app or provide INSTAGRAM_SESSIONID."
				)
				break
			except TwoFactorRequired as exc:
				last_error = exc
				if self._handle_two_factor(exc):
					continue
				break
			except PleaseWaitFewMinutes as exc:
				last_error = exc
				self._handle_rate_limit(exc)
				continue
			except ClientError as exc:
				last_error = exc
				logger.warning(
					"Instagram login failed (attempt %s/%s): %s",
					attempt,
					settings.max_retries,
					exc,
				)
				time.sleep(settings.retry_backoff_seconds * attempt)

		logger.error(
			"Instagram login failed after %s attempts. See previous logs for details.",
			settings.max_retries,
		)
		if last_error:
			raise last_error
		raise RuntimeError("Instagram authentication failed")

	def login(self) -> None:
		if self._logged_in:
			return

		session_attempted = False
		session_error: Exception | None = None

		# If a raw sessionid cookie is provided, prefer it to avoid challenges
		if settings.instagram_sessionid:
			session_attempted = True
			for attempt in range(1, settings.max_retries + 1):
				try:
					self._client.login_by_sessionid(settings.instagram_sessionid)
					self._dump_session()
					self._logged_in = True
					logger.info("Authenticated with Instagram via sessionid")
					return
				except Exception as exc:  # pragma: no cover - broad to catch instagrapi regressions
					session_error = exc
					if isinstance(exc, ClientError):
						logger.error(
							"Instagram sessionid login failed (attempt %s/%s): %s",
							attempt,
							settings.max_retries,
							exc,
						)
					else:
						logger.exception(
							"Unexpected error during Instagram sessionid login (attempt %s/%s)",
							attempt,
							settings.max_retries,
						)
					if attempt < settings.max_retries:
						time.sleep(settings.retry_backoff_seconds * attempt)
					else:
						logger.warning(
							"Instagram sessionid login exhausted %s attempts; exploring fallbacks.",
							settings.max_retries,
						)

		if self._load_session():
			return

		if settings.instagram_username and settings.instagram_password:
			if session_attempted and session_error:
				logger.info("Instagram sessionid login failed; falling back to username/password authentication")
			self._login_with_credentials()
			return

		if session_attempted:
			message = (
				"Le cookie INSTAGRAM_SESSIONID est invalide ou expiré. Fournissez un nouveau cookie ou configurez INSTAGRAM_USERNAME/PASSWORD."
			)
			raise ClientLoginRequired(message) from session_error

		raise RuntimeError("Instagram credentials are not configured (username/password or INSTAGRAM_SESSIONID)")

	def _ensure_login(self) -> None:
		if not self._logged_in:
			self.login()

	def fetch_followers(self, username: str) -> List[Dict[str, str]]:
		return self._fetch_relationship(username, relation="followers")

	def fetch_following(self, username: str) -> List[Dict[str, str]]:
		return self._fetch_relationship(username, relation="following")

	def _fetch_relationship(self, username: str, relation: str) -> List[Dict[str, str]]:
		self._ensure_login()
		fetcher = {
			"followers": self._client.user_followers,
			"following": self._client.user_following,
		}[relation]

		for attempt in range(1, settings.max_retries + 1):
			try:
				user_id = self._client.user_id_from_username(username)
				users = fetcher(user_id)
				logger.info("Fetched %s %s", len(users), relation)
				return _simplify_users(users)
			except ClientError as exc:
				logger.warning(
					"Failed to fetch %s for %s (attempt %s/%s): %s",
					relation,
					username,
					attempt,
					settings.max_retries,
					exc,
				)
				if attempt == settings.max_retries:
					raise
				time.sleep(settings.retry_backoff_seconds * attempt)

		return []  # pragma: no cover - protective

	def fetch_relationships(self, username: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
		followers = self.fetch_followers(username)
		following = self.fetch_following(username)
		return followers, following

	def get_user_profile(self, username: str) -> Dict[str, object]:
		self._ensure_login()
		retries = settings.max_retries or 1
		last_error: ClientError | None = None
		for attempt in range(1, retries + 1):
			try:
				info = self._client.user_info_by_username(username)
				if hasattr(info, "model_dump"):
					data = info.model_dump()
				elif hasattr(info, "dict"):
					data = info.dict()
				else:
					data = {
						"pk": getattr(info, "pk", None),
						"username": getattr(info, "username", username),
						"full_name": getattr(info, "full_name", ""),
						"is_private": getattr(info, "is_private", False),
						"is_verified": getattr(info, "is_verified", False),
					}
				data.setdefault("pk", getattr(info, "pk", None))
				data.setdefault("username", getattr(info, "username", username))
				data.setdefault("full_name", getattr(info, "full_name", ""))
				return data
			except ClientError as exc:
				last_error = exc
				logger.warning(
					"Lecture du profil %s échouée (tentative %s/%s): %s",
					username,
					attempt,
					retries,
					exc,
				)
				if attempt >= retries:
					raise
				time.sleep(settings.retry_backoff_seconds * attempt)
		if last_error:
			raise last_error
		raise RuntimeError("Impossible de récupérer le profil Instagram")

	def send_follow_request(self, username: str) -> Dict[str, object]:
		self._ensure_login()
		retries = settings.max_retries or 1
		last_error: ClientError | None = None
		for attempt in range(1, retries + 1):
			try:
				user_id = self._client.user_id_from_username(username)
				result = self._client.friendships_create(user_id)
				logger.info("Demande de suivi envoyée à %s", username)
				if isinstance(result, dict):
					return result
				return {"status": "ok", "result": result}
			except ClientError as exc:
				last_error = exc
				logger.warning(
					"Demande de suivi échouée pour %s (tentative %s/%s): %s",
					username,
					attempt,
					retries,
					exc,
				)
				if attempt >= retries:
					raise
				time.sleep(settings.retry_backoff_seconds * attempt)
		if last_error:
			raise last_error
		raise RuntimeError("Demande de suivi impossible")

	def close(self) -> None:
		if self._logged_in:
			try:
				self._client.logout()
			except ClientError:  # pragma: no cover - best effort
				logger.debug("Logout failed; ignoring")
		self._logged_in = False

	def __enter__(self) -> "InstaClient":
		self.login()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb) -> None:
		self.close()
