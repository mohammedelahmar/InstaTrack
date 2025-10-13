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