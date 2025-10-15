import os
from datetime import UTC, datetime, timedelta

os.environ["USE_MOCK_DB"] = "1"

from services.report_service import ReportService
from utils.storage import MongoStorage


def test_current_totals_returns_counts_and_timestamps():
	storage = MongoStorage()
	report = ReportService(storage=storage)

	now = datetime(2025, 1, 10, 12, 30, tzinfo=UTC)
	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 1, "username": "alice"}, {"pk": 2, "username": "bob"}],
		collected_at=now,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="following",
		users=[{"pk": 3, "username": "carol"}],
		collected_at=now - timedelta(hours=1),
	)

	totals = report.current_totals(target_account="demo")

	assert totals["followers_total"] == 2
	assert totals["following_total"] == 1
	assert totals["last_updated"] == now.isoformat()
	assert totals["followers_updated_at"] == now.isoformat()
	assert totals["following_updated_at"] == (now - timedelta(hours=1)).isoformat()


def test_insights_return_expected_metrics():
	storage = MongoStorage()
	report = ReportService(storage=storage)

	base_time = datetime.now(UTC)
	storage.store_changes(
		[
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time,
				"user": {"pk": 10, "username": "alice"},
			},
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time - timedelta(days=1),
				"user": {"pk": 11, "username": "bruno"},
			},
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "removed",
				"detected_at": base_time - timedelta(days=2),
				"user": {"pk": 12, "username": "claire"},
			},
			{
				"target_account": "demo",
				"list_type": "following",
				"change_type": "added",
				"detected_at": base_time - timedelta(days=1),
				"user": {"pk": 13, "username": "dylan"},
			},
			{
				"target_account": "demo",
				"list_type": "following",
				"change_type": "removed",
				"detected_at": base_time - timedelta(days=3),
				"user": {"pk": 14, "username": "erin"},
			},
		]
	)

	insights = report.insights(days=7, target_account="demo", top=2)

	assert insights["net_followers"] == 1
	assert insights["net_following"] == 0
	assert insights["total_changes"] == 5
	assert insights["positive_streak_days"] >= 1
	assert len(insights["top_new_followers"]) == 2
	assert insights["top_new_followers"][0]["username"] == "alice"
	assert len(insights["top_lost_followers"]) == 1
	assert insights["top_lost_followers"][0]["username"] == "claire"
	assert insights["best_day"] is not None
	assert insights["worst_day"] is not None


def test_recent_changes_respects_limit():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	base_time = datetime.now(UTC)
	storage.store_changes(
		[
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time - timedelta(minutes=idx),
				"user": {"pk": idx, "username": f"user{idx}"},
			}
			for idx in range(5)
		]
	)

	changes = report.recent_changes(days=7, target_account="demo", limit=3)
	assert len(changes) == 3
	assert changes[0]["username"] == "user0"
	assert changes[-1]["username"] == "user2"


def test_recent_changes_filters_by_date_range():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	base_time = datetime(2025, 3, 10, 12, tzinfo=UTC)
	storage.store_changes(
		[
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time - timedelta(days=5),
				"user": {"pk": 1, "username": "early"},
			},
			{
				"target_account": "demo",
				"list_type": "followers",
				"change_type": "added",
				"detected_at": base_time - timedelta(days=1),
				"user": {"pk": 2, "username": "window"},
			},
		]
	)

	filtered = report.recent_changes(
		start=(base_time - timedelta(days=2)).date().isoformat(),
		end=base_time.date().isoformat(),
		target_account="demo",
	)
	assert len(filtered) == 1
	assert filtered[0]["username"] == "window"


def test_compare_snapshots_returns_expected_diff():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	start_time = datetime(2025, 4, 1, 9, tzinfo=UTC)
	end_time = datetime(2025, 4, 8, 21, tzinfo=UTC)

	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 1, "username": "alice"}, {"pk": 2, "username": "bob"}],
		collected_at=start_time,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 2, "username": "bob"}, {"pk": 3, "username": "carol"}],
		collected_at=end_time,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="following",
		users=[{"pk": 10, "username": "x"}],
		collected_at=start_time,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="following",
		users=[{"pk": 10, "username": "x"}, {"pk": 11, "username": "y"}],
		collected_at=end_time,
	)

	comparison = report.compare_snapshots(
		target_account="demo",
		start=start_time.date().isoformat(),
		end=end_time.date().isoformat(),
		limit=10,
	)

	assert comparison["available"] is True
	followers_section = comparison["followers"]
	assert followers_section["added_total"] == 1
	assert followers_section["removed_total"] == 1
	assert followers_section["added"][0]["username"] == "carol"
	assert followers_section["removed"][0]["username"] == "alice"
	assert followers_section["baseline"]["count"] == 2
	assert followers_section["current"]["count"] == 2

	following_section = comparison["following"]
	assert following_section["added_total"] == 1
	assert following_section["removed_total"] == 0
	assert following_section["added"][0]["username"] == "y"


def test_snapshot_history_returns_latest_entries():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	base_time = datetime(2025, 5, 1, 8, tzinfo=UTC)
	for index in range(3):
		storage.store_snapshot(
			target_account="demo",
			list_type="followers",
			users=[{"pk": index, "username": f"user{index}"}],
			collected_at=base_time + timedelta(days=index),
		)
	for index in range(2):
		storage.store_snapshot(
			target_account="demo",
			list_type="following",
			users=[{"pk": index, "username": f"follow{index}"}],
			collected_at=base_time + timedelta(days=index),
		)

	history = report.snapshot_history(target_account="demo", limit=2)
	assert len(history["followers"]) == 2
	assert history["followers"][0]["count"] == 1
	assert history["followers"][0]["collected_at"].startswith("2025-05-03")
	assert len(history["following"]) == 2


def test_follow_back_gaps_returns_expected_lists():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	now = datetime(2025, 2, 1, 9, 0, tzinfo=UTC)

	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[
			{"pk": 1, "username": "alice", "full_name": "Alice"},
			{"pk": 2, "username": "bob", "full_name": "Bob"},
		],
		collected_at=now,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="following",
		users=[
			{"pk": 1, "username": "alice", "full_name": "Alice"},
			{"pk": 3, "username": "carol", "full_name": "Carol"},
			{"pk": 4, "username": "dave", "full_name": "Dave"},
		],
		collected_at=now,
	)

	gaps = report.follow_back_gaps(target_account="demo", limit=1)

	assert gaps["not_following_you_back"]["count"] == 2
	assert len(gaps["not_following_you_back"]["users"]) == 1
	assert gaps["not_following_you_back"]["users"][0]["username"] == "carol"
	assert gaps["you_dont_follow_back"]["count"] == 1
	assert len(gaps["you_dont_follow_back"]["users"]) == 1
	assert gaps["you_dont_follow_back"]["users"][0]["username"] == "bob"
	assert gaps["updated_at"]["followers"] == now.isoformat()
	assert gaps["updated_at"]["following"] == now.isoformat()