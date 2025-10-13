"""Coordinate snapshot collection from Instagram into MongoDB."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict, List, Optional

from config.settings import settings
from utils import comparer
from utils.insta_client import InstaClient
from utils.logger import get_logger
from utils.storage import MongoStorage, storage as default_storage


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

	def run_once(self) -> List[Dict[str, int]]:
		if not settings.target_accounts:
			raise RuntimeError("No target accounts configured. Set TARGET_ACCOUNTS in environment.")

		summaries = []
		for account in settings.target_accounts:
			summary = self._collect_for_account(account)
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


tracker_service = TrackerService()
