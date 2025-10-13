"""Reporting utilities for InstaTrack change events."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from utils.storage import MongoStorage, storage as default_storage


class ReportService:
	def __init__(self, storage: Optional[MongoStorage] = None) -> None:
		self._storage = storage or default_storage

	def recent_changes(
		self,
		*,
		days: int = 7,
		target_account: Optional[str] = None,
	) -> List[Dict[str, str]]:
		since = datetime.now(UTC) - timedelta(days=days)
		events = self._storage.changes_since(target_account=target_account, since=since)
		return [self._serialize_change(event) for event in events]

	def daily_summary(
		self,
		*,
		days: int = 7,
		target_account: Optional[str] = None,
	) -> List[Dict[str, str]]:
		since = datetime.now(UTC) - timedelta(days=days)
		events = self._storage.changes_since(target_account=target_account, since=since)

		grouped: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
		for event in events:
			day = event["detected_at"].date().isoformat()
			key = f"{event['list_type']}_{event['change_type']}"
			grouped[day][key] += 1

		summary = []
		for day in sorted(grouped.keys()):
			entry = {"date": day}
			entry.update(grouped[day])
			summary.append(entry)
		return summary

	def counts(self, *, days: int = 7, target_account: Optional[str] = None) -> Dict[str, int]:
		events = self.recent_changes(days=days, target_account=target_account)
		counters: Dict[str, int] = defaultdict(int)
		for event in events:
			key = f"{event['list_type']}_{event['change_type']}"
			counters[key] += 1
		counters.setdefault("followers_added", 0)
		counters.setdefault("followers_removed", 0)
		counters.setdefault("following_added", 0)
		counters.setdefault("following_removed", 0)
		return dict(counters)

	def export_changes_to_csv(
		self,
		file_path: Path | str,
		*,
		days: int = 7,
		target_account: Optional[str] = None,
	) -> Path:
		records = self.recent_changes(days=days, target_account=target_account)
		path = Path(file_path)
		path.parent.mkdir(parents=True, exist_ok=True)

		fieldnames = ["detected_at", "target_account", "list_type", "change_type", "username", "full_name"]

		with path.open("w", newline="", encoding="utf-8") as csvfile:
			writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
			writer.writeheader()
			for record in records:
				writer.writerow(record)

		return path

	@staticmethod
	def _serialize_change(change: Dict[str, str]) -> Dict[str, str]:
		user = change.get("user", {})
		return {
			"target_account": change.get("target_account"),
			"list_type": change.get("list_type"),
			"change_type": change.get("change_type"),
			"detected_at": change.get("detected_at").isoformat(),
			"username": user.get("username"),
			"full_name": user.get("full_name"),
		}


report_service = ReportService()
