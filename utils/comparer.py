"""Utilities for diffing Instagram relationship snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Tuple


User = Dict[str, str]


def diff_users(previous: Iterable[User], current: Iterable[User]) -> Tuple[List[User], List[User]]:
	"""Return (added, removed) comparing two sequences of user dicts."""

	prev_map = {user["pk"]: user for user in previous}
	curr_map = {user["pk"]: user for user in current}

	added = [curr_map[pk] for pk in curr_map.keys() - prev_map.keys()]
	removed = [prev_map[pk] for pk in prev_map.keys() - curr_map.keys()]

	return added, removed


def build_change_events(
	*,
	target_account: str,
	list_type: str,
	added: Iterable[User],
	removed: Iterable[User],
	detected_at: datetime,
) -> List[Dict[str, str]]:
	"""Generate Mongo documents describing relationship changes."""

	events: List[Dict[str, str]] = []
	for user in added:
		events.append(
			{
				"target_account": target_account,
				"list_type": list_type,
				"change_type": "added",
				"detected_at": detected_at,
				"user": user,
			}
		)
	for user in removed:
		events.append(
			{
				"target_account": target_account,
				"list_type": list_type,
				"change_type": "removed",
				"detected_at": detected_at,
				"user": user,
			}
		)
	return events
