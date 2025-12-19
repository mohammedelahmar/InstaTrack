"""Reporting utilities for InstaTrack change events."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, datetime, timedelta, time
from pathlib import Path
from statistics import fmean
from typing import Dict, List, Optional, Tuple

from utils.storage import MongoStorage, storage as default_storage
from utils import comparer


class ReportService:
	def __init__(self, storage: Optional[MongoStorage] = None) -> None:
		self._storage = storage or default_storage

	def recent_changes(
		self,
		*,
		days: int = 7,
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
		target_account: Optional[str] = None,
		limit: Optional[int] = None,
	) -> List[Dict[str, int | str]]:
		resolved_start, resolved_end = self._resolve_range(days=days, start=start, end=end)
		events = self._storage.changes_since(
			target_account=target_account,
			since=resolved_start,
			until=resolved_end,
			limit=limit,
		)
		return [self._serialize_change(event) for event in events]

	def daily_summary(
		self,
		*,
		days: int = 7,
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
		target_account: Optional[str] = None,
	) -> List[Dict[str, str]]:
		resolved_start, resolved_end = self._resolve_range(days=days, start=start, end=end)
		events = self._storage.changes_since(
			target_account=target_account,
			since=resolved_start,
			until=resolved_end,
		)

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

	def counts(
		self,
		*,
		days: int = 7,
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
		target_account: Optional[str] = None,
	) -> Dict[str, int]:
		events = self.recent_changes(
			days=days,
			start=start,
			end=end,
			target_account=target_account,
		)
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

		followers_updated_at = self._iso_or_none(latest_followers.get("collected_at") if latest_followers else None)
		following_updated_at = self._iso_or_none(latest_following.get("collected_at") if latest_following else None)

		last_updated_candidate = [value for value in [
			latest_followers.get("collected_at") if latest_followers else None,
			latest_following.get("collected_at") if latest_following else None,
		] if value is not None]
		last_updated = self._iso_or_none(max(last_updated_candidate)) if last_updated_candidate else None

		return {
			"followers_total": followers_count,
			"followers_updated_at": followers_updated_at,
			"following_total": following_count,
			"following_updated_at": following_updated_at,
			"last_updated": last_updated,
		}

	def follow_back_gaps(
		self,
		*,
		target_account: Optional[str] = None,
		limit: int = 25,
	) -> Dict[str, object]:
		if not target_account:
			return {
				"not_following_you_back": {"count": 0, "users": []},
				"you_dont_follow_back": {"count": 0, "users": []},
				"updated_at": {"followers": None, "following": None},
			}

		followers_snapshot = self._storage.latest_snapshot(target_account, "followers")
		following_snapshot = self._storage.latest_snapshot(target_account, "following")

		followers_users = followers_snapshot.get("users", []) if followers_snapshot else []
		following_users = following_snapshot.get("users", []) if following_snapshot else []

		followers_map = {self._user_key(user): user for user in followers_users}
		following_map = {self._user_key(user): user for user in following_users}

		def _sort_key(user: Dict[str, str]) -> tuple[str, str]:
			username = user.get("username") or ""
			full_name = user.get("full_name") or ""
			return (username.casefold(), full_name.casefold())

		not_following_back_keys = following_map.keys() - followers_map.keys()
		you_dont_follow_back_keys = followers_map.keys() - following_map.keys()

		not_following_back_all = sorted(
			(following_map[key] for key in not_following_back_keys),
			key=_sort_key,
		)
		you_dont_follow_back_all = sorted(
			(followers_map[key] for key in you_dont_follow_back_keys),
			key=_sort_key,
		)

		limit = max(0, limit)

		response = {
			"not_following_you_back": {
				"count": len(not_following_back_all),
				"users": not_following_back_all[:limit],
			},
			"you_dont_follow_back": {
				"count": len(you_dont_follow_back_all),
				"users": you_dont_follow_back_all[:limit],
			},
			"updated_at": {
				"followers": self._iso_or_none(
					followers_snapshot.get("collected_at") if followers_snapshot else None
				),
				"following": self._iso_or_none(
					following_snapshot.get("collected_at") if following_snapshot else None
				),
			},
		}

		return response

	def relationship_breakdown(
		self,
		*,
		target_account: Optional[str] = None,
		limit: int = 20,
	) -> Dict[str, object]:
		if not target_account:
			return {
				"followers_total": 0,
				"following_total": 0,
				"mutual_total": 0,
				"only_followers_total": 0,
				"only_following_total": 0,
				"mutual_ratio": 0.0,
				"updated_at": {"followers": None, "following": None},
				"samples": {
					"mutual": [],
					"only_followers": [],
					"only_following": [],
				},
			}

		followers_snapshot = self._storage.latest_snapshot(target_account, "followers")
		following_snapshot = self._storage.latest_snapshot(target_account, "following")

		followers_users = followers_snapshot.get("users", []) if followers_snapshot else []
		following_users = following_snapshot.get("users", []) if following_snapshot else []

		followers_map = {self._user_key(user): self._sanitize_user(user) for user in followers_users}
		following_map = {self._user_key(user): self._sanitize_user(user) for user in following_users}

		followers_keys = set(followers_map.keys())
		following_keys = set(following_map.keys())

		mutual_keys = followers_keys & following_keys
		only_followers_keys = followers_keys - following_keys
		only_following_keys = following_keys - followers_keys

		mutual_total = len(mutual_keys)
		followers_total = len(followers_users)
		following_total = len(following_users)
		only_followers_total = len(only_followers_keys)
		only_following_total = len(only_following_keys)

		limit = max(1, limit)

		def _sample(keys: set[str], source: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
			sorted_users = sorted((source[key] for key in keys), key=lambda user: (
				(user.get("username") or "").casefold(),
				(user.get("full_name") or "").casefold(),
			))
			return sorted_users[:limit]

		updated_at = {
			"followers": self._iso_or_none(followers_snapshot.get("collected_at") if followers_snapshot else None),
			"following": self._iso_or_none(following_snapshot.get("collected_at") if following_snapshot else None),
		}

		mutual_ratio = round(mutual_total / followers_total, 4) if followers_total else 0.0

		return {
			"followers_total": followers_total,
			"following_total": following_total,
			"mutual_total": mutual_total,
			"only_followers_total": only_followers_total,
			"only_following_total": only_following_total,
			"mutual_ratio": mutual_ratio,
			"updated_at": updated_at,
			"samples": {
				"mutual": _sample(mutual_keys, followers_map),
				"only_followers": _sample(only_followers_keys, followers_map),
				"only_following": _sample(only_following_keys, following_map),
			},
		}

	def insights(
		self,
		*,
		days: int = 7,
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
		target_account: Optional[str] = None,
		top: int = 5,
	) -> Dict[str, object | None]:
		recent = self.recent_changes(
			days=days,
			start=start,
			end=end,
			target_account=target_account,
		)
		counts = self.counts(
			days=days,
			start=start,
			end=end,
			target_account=target_account,
		)
		daily = self.daily_summary(
			days=days,
			start=start,
			end=end,
			target_account=target_account,
		)

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
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
		target_account: Optional[str] = None,
	) -> Path:
		records = self.recent_changes(
			days=days,
			start=start,
			end=end,
			target_account=target_account,
		)
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

	@staticmethod
	def _iso_or_none(value: datetime | None) -> str | None:
		if value is None:
			return None
		if value.tzinfo is None:
			value = value.replace(tzinfo=UTC)
		return value.isoformat()

	@staticmethod
	def _user_key(user: Dict[str, object]) -> str:
		pk = user.get("pk")
		if pk is not None:
			return str(pk)
		username = user.get("username")
		if isinstance(username, str) and username:
			return f"username:{username.lower()}"
		full_name = user.get("full_name")
		if isinstance(full_name, str) and full_name:
			return f"full:{full_name.lower()}"
		return repr(sorted(user.items()))

	@staticmethod
	def _sanitize_user(user: Dict[str, object]) -> Dict[str, object]:
		return {
			"pk": user.get("pk"),
			"username": user.get("username"),
			"full_name": user.get("full_name"),
			"is_private": user.get("is_private"),
		}

	@staticmethod
	def _parse_date(value: str, *, end_of_day: bool = False) -> Optional[datetime]:
		try:
			if len(value) == 10:
				# Assume YYYY-MM-DD
				year, month, day = map(int, value.split("-"))
				time_part = time(23, 59, 59, 999999) if end_of_day else time(0, 0)
				dt = datetime(year, month, day, time_part.hour, time_part.minute, time_part.second, time_part.microsecond, tzinfo=UTC)
			else:
				dt = datetime.fromisoformat(value)
			if dt.tzinfo is None:
				dt = dt.replace(tzinfo=UTC)
			return dt
		except ValueError:
			return None

	def _resolve_range(
		self,
		*,
		days: int = 7,
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
	) -> Tuple[datetime, datetime]:
		if isinstance(start, str):
			start_dt = self._parse_date(start)
		elif isinstance(start, datetime):
			start_dt = start
		else:
			start_dt = None

		if isinstance(end, str):
			end_dt = self._parse_date(end, end_of_day=True)
		elif isinstance(end, datetime):
			end_dt = end
		else:
			end_dt = None

		now = datetime.now(UTC)
		if start_dt and not end_dt:
			end_dt = now
		if end_dt and not start_dt:
			start_dt = end_dt - timedelta(days=days)

		if not start_dt or not end_dt:
			end_dt = now
			start_dt = now - timedelta(days=days)

		if start_dt.tzinfo is None:
			start_dt = start_dt.replace(tzinfo=UTC)
		if end_dt.tzinfo is None:
			end_dt = end_dt.replace(tzinfo=UTC)

		if start_dt > end_dt:
			start_dt, end_dt = end_dt, start_dt

		return start_dt, end_dt

	def compare_snapshots(
		self,
		*,
		target_account: Optional[str],
		start: Optional[str | datetime],
		end: Optional[str | datetime],
		limit: int = 50,
	) -> Dict[str, object]:
		if not target_account:
			return {
				"available": False,
				"range": {"start": None, "end": None},
			}

		start_dt, end_dt = self._resolve_range(days=7, start=start, end=end)
		limit = max(1, limit)
		comparisons: Dict[str, Dict[str, object]] = {}

		for list_type in ("followers", "following"):
			baseline = self._storage.snapshot_at(
				target_account=target_account,
				list_type=list_type,
				moment=start_dt,
			)
			if baseline is None:
				baseline = self._storage.snapshot_at(
					target_account=target_account,
					list_type=list_type,
					moment=start_dt,
					direction="after",
				)

			current = self._storage.snapshot_at(
				target_account=target_account,
				list_type=list_type,
				moment=end_dt,
			)
			if current is None:
				current = self._storage.latest_snapshot(target_account, list_type)

			if not baseline or not current:
				comparisons[list_type] = {
					"available": False,
					"baseline": None,
					"current": None,
					"added": [],
					"removed": [],
				}
				continue

			baseline_users = baseline.get("users", [])
			current_users = current.get("users", [])
			added, removed = comparer.diff_users(baseline_users, current_users)

			comparisons[list_type] = {
				"available": True,
				"baseline": {
					"collected_at": self._iso_or_none(baseline.get("collected_at")),
					"count": len(baseline_users),
				},
				"current": {
					"collected_at": self._iso_or_none(current.get("collected_at")),
					"count": len(current_users),
				},
				"added": sorted(
					added,
					key=lambda user: (
						(user.get("username") or "").casefold(),
						(user.get("full_name") or "").casefold(),
					),
				)[:limit],
				"removed": sorted(
					removed,
					key=lambda user: (
						(user.get("username") or "").casefold(),
						(user.get("full_name") or "").casefold(),
					),
				)[:limit],
				"added_total": len(added),
				"removed_total": len(removed),
			}

		return {
			"available": any(section["available"] for section in comparisons.values()),
			"range": {
				"start": self._iso_or_none(start_dt),
				"end": self._iso_or_none(end_dt),
			},
			"followers": comparisons.get("followers", {}),
			"following": comparisons.get("following", {}),
		}

	def snapshot_history(
		self,
		*,
		target_account: Optional[str],
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
		limit: int = 20,
	) -> Dict[str, List[Dict[str, object]]]:
		if not target_account:
			return {"followers": [], "following": []}
		start_dt, end_dt = self._resolve_range(days=365, start=start, end=end)
		limit = max(1, limit)
		result: Dict[str, List[Dict[str, object]]] = {}
		for list_type in ("followers", "following"):
			snapshots = self._storage.snapshot_history(
				target_account=target_account,
				list_type=list_type,
				start=start_dt,
				end=end_dt,
				limit=limit,
			)
			entries: List[Dict[str, object]] = []
			for snapshot in snapshots:
				entries.append(
					{
						"collected_at": self._iso_or_none(snapshot.get("collected_at")),
						"count": len(snapshot.get("users", [])),
					}
				)
			result[list_type] = entries
		return result

	def followers_history(
		self,
		*,
		target_account: Optional[str],
		start: Optional[str | datetime] = None,
		end: Optional[str | datetime] = None,
		limit: int = 50,
	) -> List[Dict[str, object]]:
		if not target_account:
			return []
		start_dt, end_dt = self._resolve_range(days=365, start=start, end=end)
		limit = max(1, limit)
		snapshots = self._storage.snapshot_history(
			target_account=target_account,
			list_type="followers",
			start=start_dt,
			end=end_dt,
			limit=limit,
		)
		history: List[Dict[str, object]] = []
		for snapshot in snapshots:
			users = snapshot.get("users", []) or []
			sanitized_users = []
			for user in users:
				sanitized_users.append(
					{
						"pk": user.get("pk"),
						"username": user.get("username"),
						"full_name": user.get("full_name"),
					}
				)
			history.append(
				{
					"collected_at": self._iso_or_none(snapshot.get("collected_at")),
					"count": len(sanitized_users),
					"users": sanitized_users,
				}
			)
		return history

report_service = ReportService()
