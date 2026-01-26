"""Coordinate snapshot collection from Instagram into MongoDB."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List, Optional

from config.settings import settings
from utils import comparer
from utils.insta_client import InstaClient
from utils.logger import get_logger
from utils.storage import MongoStorage, storage as default_storage
import requests
import json


logger = get_logger(__name__)


class TrackerService:
	"""High-level orchestration of Instagram snapshot collection."""

	def __init__(
		self,
		*,
		client: Optional[InstaClient] = None,
		storage: Optional[MongoStorage] = None,
	) -> None:
		self._client = client or InstaClient()
		self._storage = storage or default_storage

	def run_once(self, single_account: Optional[str] = None) -> List[Dict[str, int]]:
		if not settings.target_accounts:
			raise RuntimeError("No target accounts configured. Set TARGET_ACCOUNTS in environment.")

		targets = settings.target_accounts
		if single_account:
			if single_account not in targets:
				raise RuntimeError(f"Account '{single_account}' is not in the configured targets list.")
			targets = [single_account]

		summaries = []
		for account in targets:
			summary = self._collect_for_account(account)
			self._send_notification(summary)
			summaries.append(summary)

		return summaries

	def _collect_for_account(self, account: str) -> Dict[str, int]:
		logger.info("Collecting snapshots for %s", account)
		followers, following = self._client.fetch_relationships(account)
		detected_at = datetime.now(UTC)

		follower_summary = self._process_list(
			account=account,
			list_type="followers",
			current_users=followers,
			detected_at=detected_at,
		)

		following_summary = self._process_list(
			account=account,
			list_type="following",
			current_users=following,
			detected_at=detected_at,
		)

		return {
			"target_account": account,
			"followers_added": follower_summary["added"],
			"followers_removed": follower_summary["removed"],
			"following_added": following_summary["added"],
			"following_removed": following_summary["removed"],
		}

	def _send_notification(self, summary: Dict[str, object]) -> None:
		if not settings.discord_webhook_url:
			return
		
		changes = []
		if summary["followers_added"] > 0:
			changes.append(f"📈 +{summary['followers_added']} followers")
		if summary["followers_removed"] > 0:
			changes.append(f"📉 -{summary['followers_removed']} followers")
		if summary["following_added"] > 0:
			changes.append(f"👤 +{summary['following_added']} following")
		if summary["following_removed"] > 0:
			changes.append(f"👻 -{summary['following_removed']} following")
			
		if not changes:
			return
			
		account = summary["target_account"]
		message = {
			"embeds": [{
				"title": f"Changements détectés pour {account}",
				"description": "\n".join(changes),
				"color": 3447003, # Greenish
				"timestamp": datetime.now(UTC).isoformat()
			}]
		}
		
		try:
			requests.post(settings.discord_webhook_url, json=message, timeout=5)
		except Exception as e:
			logger.error("Failed to send Discord notification: %s", e)

	def _process_list(
		self,
		*,
		account: str,
		list_type: str,
		current_users: List[Dict[str, str]],
		detected_at: datetime,
	) -> Dict[str, int]:
		previous_snapshot = self._storage.latest_snapshot(account, list_type)
		previous_users = previous_snapshot.get("users", []) if previous_snapshot else []

		added, removed = comparer.diff_users(previous_users, current_users)
		events = comparer.build_change_events(
			target_account=account,
			list_type=list_type,
			added=added,
			removed=removed,
			detected_at=detected_at,
		)

		self._storage.store_snapshot(
			target_account=account,
			list_type=list_type,
			users=current_users,
			collected_at=detected_at,
		)
		self._storage.store_changes(events)



		logger.info(
			"%s: %s added, %s removed for %s",
			list_type,
			len(added),
			len(removed),
			account,
		)

		return {"added": len(added), "removed": len(removed)}

	def get_live_profile(self, username: str, target: Optional[str] = None) -> Dict[str, object]:
		"""Fetch fresh profile details on demand."""
		# Use single retry for UI responsiveness
		profile = self._client.get_user_profile(username, retries=1)

		if target:
			try:
				# Contextualize friendship status relative to the target account using local data
				followers_snap = self._storage.latest_snapshot(target, "followers")
				following_snap = self._storage.latest_snapshot(target, "following")

				followers_set = {u.get("username") for u in (followers_snap.get("users") or [])} if followers_snap else set()
				following_set = {u.get("username") for u in (following_snap.get("users") or [])} if following_snap else set()

				# "follows_viewer" -> Does the profile follow the target?
				profile["follows_viewer"] = username in followers_set
				# "followed_by_viewer" -> Does the target follow the profile?
				profile["followed_by_viewer"] = username in following_set

				logger.info(
					"Contextualized profile %s for target %s: follows_target=%s, followed_by_target=%s",
					username,
					target,
					profile["follows_viewer"],
					profile["followed_by_viewer"]
				)
			except Exception as exc:
				logger.warning("Failed to contextualize profile for target %s: %s", target, exc)

		return profile


tracker_service = TrackerService()
