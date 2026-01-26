"""Wrapper around instagrapi for follower/following snapshots."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
from pydantic import ValidationError
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
					"profile_pic_url": str(getattr(info, "profile_pic_url", "")),
					"is_private": getattr(info, "is_private", False),
					"is_verified": getattr(info, "is_verified", False),
					"follows_viewer": getattr(info, "follows_viewer", False),
					"followed_by_viewer": getattr(info, "followed_by_viewer", False),
				}
		simplified.append(
			{
				"pk": user_id,
				"username": data.get("username", ""),
				"full_name": data.get("full_name", ""),
				"profile_pic_url": str(data.get("profile_pic_url", "")),
				"is_private": data.get("is_private", False),
				"is_verified": data.get("is_verified", False),
			}
		)
	return simplified


def _normalize_friendship_status(result: Any) -> Dict[str, Any]:
	"""Standardize instagrapi follow result into a dict."""
	if isinstance(result, dict):
		# Raw API response or dict
		return result
	
	# Handle Pydantic models (FriendshipStatus) or objects
	data = {}
	if hasattr(result, "model_dump"):
		data = result.model_dump()
	elif hasattr(result, "dict"):
		data = result.dict()
	elif result is True:
		# Legacy/Simple boolean return
		return {"following": True, "outgoing_request": False}
	elif result is False:
		return {"following": False, "outgoing_request": False}
	else:
		# Object access attempt
		data = {
			"following": getattr(result, "following", False),
			"outgoing_request": getattr(result, "outgoing_request", False),
			"is_private": getattr(result, "is_private", False),
		}
	
	return data


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


	def _reset_login_state(self, *, clear_session_file: bool = False) -> None:
		"""Recreate the underlying client and optionally drop the cached session."""

		try:
			if clear_session_file and self._session_path.exists():
				self._session_path.unlink()
		except OSError as exc:  # pragma: no cover - best effort cleanup
			logger.warning("Impossible de supprimer la session Instagram obsolète: %s", exc)

		self._logged_in = False
		self._client = Client()
		self._client.delay_range = (settings.min_request_delay, settings.max_request_delay)

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

		# 1) Try cached session first (has full settings/device), then fall back to raw sessionid or credentials.
		if self._load_session():
			return

		# 2) Raw sessionid path
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
					invalid_session = isinstance(exc, (ClientLoginRequired, ValidationError, KeyError)) or "login_required" in str(exc).lower()
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

					# Some instagrapi versions throw KeyError/ValidationError when public GraphQL fails even with a valid cookie.
					# In that case, try loading the cached session file before giving up.
					if invalid_session and self._load_session():
						logger.info("Session restaurée depuis le cache après échec login_by_sessionid")
						return

					# IMPACT: instagrapi throws ValidationError/KeyError during verify even if cookies are set.
					# If the user provides a session ID, we should trust it if the library is just being strict.
					if invalid_session and self._client.private.cookies.get("sessionid") == settings.instagram_sessionid:
						logger.warning("Instagrapi verification failed (%s) but sessionid cookie is set. Forcing login success.", exc)
						self._dump_session()
						self._logged_in = True
						return

					if invalid_session:
						raise ClientLoginRequired(
							"Le cookie INSTAGRAM_SESSIONID semble invalide ou expiré. Fournissez un nouveau cookie depuis Instagram."
						) from exc
					if attempt < settings.max_retries:
						time.sleep(settings.retry_backoff_seconds * attempt)
					else:
						logger.warning(
							"Instagram sessionid login exhausted %s attempts; exploring fallbacks.",
							settings.max_retries,
						)

		# 3) Credentials fallback
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

		# instagrapi caches relationship lists in-memory; force a fresh fetch each time so
		# successive "Lancer une capture" calls see new followers/following without
		# restarting the app.
		try:
			cache = getattr(self._client, "cache", None)
			if cache and hasattr(cache, "clear"):
				cache.clear()
		except Exception:  # pragma: no cover - best effort cache reset
			logger.debug("Failed to clear instagrapi cache before fetch", exc_info=True)

		for attempt in range(1, settings.max_retries + 1):
			try:
				user_id = self._client.user_id_from_username(username)
				try:
					users = fetcher(user_id, use_cache=False)
				except TypeError:
					# Older instagrapi versions may not support use_cache; fall back to default call.
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

	def get_user_profile(self, username: str, retries: int | None = None) -> Dict[str, object]:
		self._ensure_login()
		# Clear instagrapi cache to avoid stale profile data
		try:
			cache = getattr(self._client, "cache", None)
			if cache and hasattr(cache, "clear"):
				cache.clear()
		except Exception:
			pass

		max_tries = retries if retries is not None else (settings.max_retries or 1)
		last_error: ClientError | None = None
		for attempt in range(1, max_tries + 1):
			try:
				# Use private API v1 directly to skip flaky public requests (speed up)
				info = self._client.user_info_by_username_v1(username)
				print(f"DEBUG: Fetched info for {username}")
				print(f"DEBUG: follows_viewer={getattr(info, 'follows_viewer', 'MISSING')}")
				print(f"DEBUG: followed_by_viewer={getattr(info, 'followed_by_viewer', 'MISSING')}")
				# Try to check if there is a 'friendship_status' attribute or dict
				if hasattr(info, 'friendship_status'):
					print(f"DEBUG: friendship_status={info.friendship_status}")
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
						"profile_pic_url": str(getattr(info, "profile_pic_url", "")),
						"biography": getattr(info, "biography", ""),
						"external_url": getattr(info, "external_url", ""),
						"media_count": getattr(info, "media_count", 0),
						"follower_count": getattr(info, "follower_count", 0),
						"following_count": getattr(info, "following_count", 0),
					}
				data.setdefault("pk", getattr(info, "pk", None))
				data.setdefault("username", getattr(info, "username", username))
				data.setdefault("full_name", getattr(info, "full_name", ""))
				
				# Friendship Status Fallback
				follows_viewer = getattr(info, "follows_viewer", None)
				followed_by_viewer = getattr(info, "followed_by_viewer", None)

				if follows_viewer is None or followed_by_viewer is None:
					try:
						# Explicitly fetch friendship status if missing
						logger.info(f"Fetching explicit friendship status for {username}...")
						friendship = self._client.user_friendship_v1(data["pk"])
						follows_viewer = friendship.followed_by  # They follow me
						followed_by_viewer = friendship.following # I follow them
						print(f"DEBUG: Explicit friendship fetch: follows_viewer={follows_viewer}")
					except Exception as e:
						logger.warning(f"Failed to fetch friendship status: {e}")
						follows_viewer = False
						followed_by_viewer = False

				data["follows_viewer"] = follows_viewer
				data["followed_by_viewer"] = followed_by_viewer
				return data
			except ClientError as exc:
				last_error = exc
				if "login_required" in str(exc).lower():
					raise ClientLoginRequired("Session Instagram expirée ou invalide.") from exc
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
		# instagrapi renamed the follow method in some releases. Prefer friendships_create
		# when available, otherwise fall back to user_follow.
		if hasattr(self._client, "friendships_create"):
			follow_call = self._client.friendships_create  # type: ignore[attr-defined]
		elif hasattr(self._client, "user_follow"):
			follow_call = self._client.user_follow  # type: ignore[attr-defined]
		else:  # pragma: no cover - defensive guard for unexpected client versions
			raise RuntimeError("Le client Instagram ne supporte pas l'envoi de demandes de suivi.")
		for attempt in range(1, retries + 1):
			try:
				user_id = self._client.user_id_from_username(username)
				# 1. Check if we are already following to avoid spam
				# (optional, but good practice. For now, trust the user's click)

				# 2. Perform follow
				raw_result = follow_call(user_id)
				logger.info("Follow request sent to %s (result type: %s)", username, type(raw_result))
				
				# 3. Normalize result
				normalized = _normalize_friendship_status(raw_result)
				
				# 4. Return standard structure
				# API often returns the friendship_status object directly, or wrapped.
				# We flatten it to a clean dict for the service layer.
				return {
					"status": "ok",
					"following": bool(normalized.get("following")),
					"outgoing_request": bool(normalized.get("outgoing_request")),
					"raw": str(raw_result),
				}
			except ClientLoginRequired as exc:
				# Check if this is actually a 403 Action Block masquerading as LoginRequired
				response = getattr(exc, "response", None)
				if response and response.status_code == 403:
					logger.error("Instagram 403 Forbidden on follow action. Likely 'Action Blocked'.")
					raise ClientError("Action bloquée par Instagram (403). Réessayez plus tard.") from exc

				# Session/cookie expired: try to recycle cached session before failing.
				logger.error(
					"Session Instagram expirée ou invalide: tentative de reconnexion (%s/%s)",
					attempt,
					retries,
				)
				if attempt < retries:
					self._reset_login_state(clear_session_file=False)
					self.login()
					time.sleep(settings.retry_backoff_seconds * attempt)
					continue
				raise
			except ClientError as exc:
				last_error = exc
				if "login_required" in str(exc).lower():
					logger.error(
						"Instagram a renvoyé login_required pendant l'envoi de la demande (%s/%s); nouvelle connexion…",
						attempt,
						retries,
					)
					if attempt < retries:
						self._reset_login_state(clear_session_file=False)
						self.login()
						time.sleep(settings.retry_backoff_seconds * attempt)
						continue
					raise ClientLoginRequired("Session Instagram expirée ou invalide.") from exc
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

	def get_user_medias(self, username: str, amount: int = 10) -> List[Dict[str, object]]:
		"""Fetch recent medias for a user."""
		self._ensure_login()
		try:
			user_id = self._client.user_id_from_username(username)
			medias = self._client.user_medias(user_id, amount=amount)
			return [
				{
					"pk": m.pk,
					"id": m.id,
					"code": m.code,
					"media_type": m.media_type,
					"like_count": m.like_count,
					"comment_count": m.comment_count,
				}
				for m in medias
			]
		except Exception as e:
			logger.error(f"Failed to fetch medias for {username}: {e}")
			return []

	def get_media_likers(self, media_id: str) -> List[str]:
		"""Fetch usernames of users who liked the media."""
		self._ensure_login()
		try:
			users = self._client.media_likers(media_id)
			return [u.username for u in users]
		except Exception as e:
			logger.warning(f"Failed to fetch likers for {media_id}: {e}")
			return []

	def get_media_comments(self, media_id: str) -> List[str]:
		"""Fetch usernames of users who commented on the media."""
		self._ensure_login()
		try:
			# fetch last 50 comments to get a good sample
			comments = self._client.media_comments(media_id, amount=50)
			return [c.user.username for c in comments]
		except Exception as e:
			logger.warning(f"Failed to fetch comments for {media_id}: {e}")
			return []

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
