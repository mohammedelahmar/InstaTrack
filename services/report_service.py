"""Reporting utilities for InstaTrack change events."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import fmean
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
		limit: Optional[int] = None,
	) -> List[Dict[str, int | str]]:
		since = datetime.now(UTC) - timedelta(days=days)
		events = self._storage.changes_since(
			target_account=target_account,
			since=since,
			limit=limit,
		)
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
			bucket = grouped[day]
			followers_added = bucket.get("followers_added", 0)
			followers_removed = bucket.get("followers_removed", 0)
			following_added = bucket.get("following_added", 0)
			following_removed = bucket.get("following_removed", 0)

			entry.update(
				{
					"followers_added": followers_added,
					"followers_removed": followers_removed,
					"following_added": following_added,
					"following_removed": following_removed,
					"followers_net": followers_added - followers_removed,
					"following_net": following_added - following_removed,
					"total_changes": followers_added
					+ followers_removed
					+ following_added
					+ following_removed,
				}
			)
			summary.append(entry)
		return summary

	def counts(self, *, days: int = 7, target_account: Optional[str] = None) -> Dict[str, int]:
		events = self.recent_changes(days=days, target_account=target_account)
		counters: Dict[str, int] = defaultdict(int)
		for event in events:
			key = f"{event['list_type']}_{event['change_type']}"
			counters[key] += 1
		followers_added = counters.setdefault("followers_added", 0)
		followers_removed = counters.setdefault("followers_removed", 0)
		following_added = counters.setdefault("following_added", 0)
		following_removed = counters.setdefault("following_removed", 0)
		counters["followers_net"] = followers_added - followers_removed
		counters["following_net"] = following_added - following_removed
		counters["total_changes"] = (
			followers_added + followers_removed + following_added + following_removed
		)
		return dict(counters)

	def current_totals(self, *, target_account: Optional[str] = None) -> Dict[str, int | str | None]:
		if not target_account:
			return {
				"followers_total": 0,
				"followers_updated_at": None,
				"following_total": 0,
				"following_updated_at": None,
				"last_updated": None,
			}

		latest_followers = self._storage.latest_snapshot(target_account, "followers")
		latest_following = self._storage.latest_snapshot(target_account, "following")

		followers_count = len(latest_followers.get("users", [])) if latest_followers else 0
		following_count = len(latest_following.get("users", [])) if latest_following else 0

		def _iso_or_none(value: datetime | None) -> str | None:
			if value is None:
				return None
			if value.tzinfo is None:
				value = value.replace(tzinfo=UTC)
			return value.isoformat()

		followers_updated_at = _iso_or_none(latest_followers.get("collected_at") if latest_followers else None)
		following_updated_at = _iso_or_none(latest_following.get("collected_at") if latest_following else None)

		last_updated_candidate = [value for value in [
			latest_followers.get("collected_at") if latest_followers else None,
			latest_following.get("collected_at") if latest_following else None,
		] if value is not None]
		last_updated = _iso_or_none(max(last_updated_candidate)) if last_updated_candidate else None

		return {
			"followers_total": followers_count,
			"followers_updated_at": followers_updated_at,
			"following_total": following_count,
			"following_updated_at": following_updated_at,
			"last_updated": last_updated,
		}

	def insights(
		self,
		*,
		days: int = 7,
		target_account: Optional[str] = None,
		top: int = 5,
	) -> Dict[str, object | None]:
		recent = self.recent_changes(days=days, target_account=target_account)
		counts = self.counts(days=days, target_account=target_account)
		daily = self.daily_summary(days=days, target_account=target_account)

		net_followers_series = [entry.get("followers_net", 0) for entry in daily]
		net_following_series = [entry.get("following_net", 0) for entry in daily]

		positive_streak = 0
		current_streak = 0
		for value in net_followers_series:
			if value > 0:
				current_streak += 1
				positive_streak = max(positive_streak, current_streak)
			else:
				current_streak = 0

		best_day = None
		worst_day = None
		if daily:
			best_entry = max(daily, key=lambda entry: entry.get("followers_net", 0))
			worst_entry = min(daily, key=lambda entry: entry.get("followers_net", 0))
			best_day = {
				"date": best_entry["date"],
				"followers_net": best_entry.get("followers_net", 0),
				"following_net": best_entry.get("following_net", 0),
				"total_changes": best_entry.get("total_changes", 0),
			}
			worst_day = {
				"date": worst_entry["date"],
				"followers_net": worst_entry.get("followers_net", 0),
				"following_net": worst_entry.get("following_net", 0),
				"total_changes": worst_entry.get("total_changes", 0),
			}

		top_new_followers = [
			change
			for change in recent
			if change.get("list_type") == "followers" and change.get("change_type") == "added"
		][:top]
		top_lost_followers = [
			change
			for change in recent
			if change.get("list_type") == "followers" and change.get("change_type") == "removed"
		][:top]

		average_followers = round(fmean(net_followers_series), 2) if net_followers_series else 0.0
		average_following = round(fmean(net_following_series), 2) if net_following_series else 0.0

		latest_activity = recent[0] if recent else None

		return {
			"net_followers": counts.get("followers_net", 0),
			"net_following": counts.get("following_net", 0),
			"total_changes": counts.get("total_changes", 0),
			"positive_streak_days": positive_streak,
			"average_daily_followers": average_followers,
			"average_daily_following": average_following,
			"best_day": best_day,
			"worst_day": worst_day,
			"top_new_followers": top_new_followers,
			"top_lost_followers": top_lost_followers,
			"latest_activity": latest_activity,
		}

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
