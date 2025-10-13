"""MongoDB persistence helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from config.settings import settings
from utils.logger import get_logger


logger = get_logger(__name__)


class MongoStorage:
	"""Encapsulate MongoDB access for snapshots and change events."""

	SNAPSHOTS_COLLECTION = settings.mongo_snapshots_collection
	CHANGES_COLLECTION = settings.mongo_changes_collection

	def __init__(self) -> None:
		self._client = self._init_client()
		self._db = self._client[settings.mongo_db]
		self._ensure_indexes()

	def _init_client(self) -> MongoClient:
		if settings.use_mock_db:
			return self._build_mock_client()

		try:
			client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
			client.admin.command("ping")
			return client
		except PyMongoError as exc:
			logger.warning(
				"Failed to connect to MongoDB at %s (%s). Falling back to in-memory mongomock.",
				settings.mongo_uri,
				exc,
			)
			return self._build_mock_client()

	@staticmethod
	def _build_mock_client() -> MongoClient:
		try:
			import mongomock

			logger.info("Using mongomock in-memory database")
			return mongomock.MongoClient()
		except ImportError as exc:  # pragma: no cover - defensive branch
			raise RuntimeError(
				"mongomock must be installed to use the in-memory fallback database"
			) from exc

	def _ensure_indexes(self) -> None:
		snapshots = self._db[self.SNAPSHOTS_COLLECTION]
		changes = self._db[self.CHANGES_COLLECTION]

		snapshots.create_index(
			[
				("target_account", ASCENDING),
				("list_type", ASCENDING),
				("collected_at", ASCENDING),
			],
			name="snapshot_lookup",
		)

		changes.create_index(
			[
				("target_account", ASCENDING),
				("detected_at", ASCENDING),
			],
			name="changes_lookup",
		)

	def _collection(self, name: str) -> Collection:
		return self._db[name]

	def store_snapshot(
		self,
		*,
		target_account: str,
		list_type: str,
		users: Iterable[Dict[str, Any]],
		collected_at: Optional[datetime] = None,
	) -> str:
		collected_at = collected_at or datetime.now(UTC)
		doc = {
			"target_account": target_account,
			"list_type": list_type,
			"users": list(users),
			"collected_at": collected_at,
		}

		result = self._collection(self.SNAPSHOTS_COLLECTION).insert_one(doc)
		logger.debug("Stored snapshot", extra={"target": target_account, "list_type": list_type})
		return str(result.inserted_id)

	def latest_snapshot(self, target_account: str, list_type: str) -> Optional[Dict[str, Any]]:
		cursor = (
			self._collection(self.SNAPSHOTS_COLLECTION)
			.find({"target_account": target_account, "list_type": list_type})
			.sort("collected_at", -1)
			.limit(1)
		)
		try:
			return next(cursor)
		except StopIteration:
			return None

	def store_changes(self, changes: Iterable[Dict[str, Any]]) -> int:
		changes = list(changes)
		if not changes:
			return 0
		self._collection(self.CHANGES_COLLECTION).insert_many(changes)
		logger.debug("Stored %s change events", len(changes))
		return len(changes)

	def changes_since(
		self,
		*,
		target_account: Optional[str] = None,
		since: Optional[datetime] = None,
	) -> List[Dict[str, Any]]:
		query: Dict[str, Any] = {}
		if target_account:
			query["target_account"] = target_account
		if since:
			query["detected_at"] = {"$gte": since}

		cursor = (
			self._collection(self.CHANGES_COLLECTION)
			.find(query)
			.sort("detected_at", -1)
		)
		return list(cursor)


storage = MongoStorage()
