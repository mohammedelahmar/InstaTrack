"""Flask application exposing InstaTrack dashboard."""

from __future__ import annotations

import csv
import io
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

try:  # pragma: no cover - optional dependency handling for type checkers
	from apscheduler.schedulers.base import SchedulerAlreadyRunningError
except ImportError:  # pragma: no cover - fallback when APScheduler changes API
	SchedulerAlreadyRunningError = Exception  # type: ignore

from config.settings import settings
from services.report_service import ReportService, report_service as default_report_service
from services.tracker_service import TrackerService, tracker_service as default_tracker_service
from utils.scheduler import TrackerScheduler

try:  # pragma: no cover - optional dependency imported defensively
	from instagrapi.exceptions import ClientError as InstaClientError
	from instagrapi.exceptions import ClientLoginRequired as InstaClientLoginRequired
except ImportError:  # pragma: no cover - instagrapi not installed or optional in tests
	InstaClientError = InstaClientLoginRequired = Exception  # type: ignore


_scheduler_instance: Optional[TrackerScheduler] = None


def _get_scheduler(tracker: TrackerService) -> TrackerScheduler:
	global _scheduler_instance
	if _scheduler_instance is None:
		_scheduler_instance = TrackerScheduler(tracker)
	return _scheduler_instance


def create_app(reports: ReportService | None = None, tracker: TrackerService | None = None) -> Flask:
	app = Flask(__name__, static_folder="static", template_folder="templates")
	report_provider = reports or default_report_service
	tracker_provider = tracker or default_tracker_service

	@app.route("/")
	def dashboard():
		account = request.args.get("account")
		accounts = settings.target_accounts
		default_account = account or (accounts[0] if accounts else None)
		timeframes = [7, 14, 30]
		try:
			days = int(request.args.get("days", timeframes[0]))
		except (TypeError, ValueError):
			days = timeframes[0]
		if days not in timeframes:
			days = timeframes[0]
		change_limit = 250

		counts = report_provider.counts(days=days, target_account=default_account)
		changes = report_provider.recent_changes(
			days=days,
			target_account=default_account,
			limit=change_limit,
		)
		daily = report_provider.daily_summary(days=days, target_account=default_account)
		totals = report_provider.current_totals(target_account=default_account)
		insights = report_provider.insights(days=days, target_account=default_account)

		return render_template(
			"dashboard.html",
			counts=counts,
			changes=changes,
			daily=daily,
			totals=totals,
			insights=insights,
			accounts=accounts,
			default_account=default_account,
			timeframes=timeframes,
			selected_days=days,
			change_limit=change_limit,
		)

	@app.route("/api/snapshot", methods=["POST"])
	def api_snapshot():
		try:
			summaries = tracker_provider.run_once()
			return jsonify({"status": "ok", "summaries": summaries}), 200
		except InstaClientLoginRequired as exc:
			app.logger.warning("Instagram session expired or login required: %s", exc)
			message = (
				"La session Instagram a expiré. Fournissez un nouvel INSTAGRAM_SESSIONID ou relancez la connexion."
			)
			return jsonify({"status": "error", "message": message}), 400
		except InstaClientError as exc:
			app.logger.error("Instagram API error during snapshot: %s", exc)
			message = (
				"Impossible de contacter Instagram: {detail}. Vérifiez vos identifiants ou attendez quelques minutes."
			).format(detail=str(exc))
			return jsonify({"status": "error", "message": message}), 502
		except RuntimeError as exc:
			app.logger.warning("Snapshot aborted: %s", exc)
			return jsonify({"status": "error", "message": str(exc)}), 400
		except Exception as exc:  # pragma: no cover - defensive logging
			app.logger.exception("Snapshot execution failed")
			return jsonify({"status": "error", "message": "Erreur interne lors de la capture."}), 500

	@app.route("/api/report")
	def api_report():
		days = int(request.args.get("days", 7))
		account = request.args.get("account") or None
		preview_limit = int(request.args.get("preview_limit", 20))
		preview_limit = max(1, min(preview_limit, 200))

		counts = report_provider.counts(days=days, target_account=account)
		insights = report_provider.insights(days=days, target_account=account)
		recent = report_provider.recent_changes(
			days=days,
			target_account=account,
			limit=preview_limit,
		)
		totals = report_provider.current_totals(target_account=account)
		return jsonify(
			{
				"status": "ok",
				"counts": counts,
				"insights": insights,
				"recent": recent,
				"totals": totals,
			}
		)

	@app.route("/api/schedule", methods=["POST"])
	def api_schedule():
		scheduler = _get_scheduler(tracker_provider)
		try:
			scheduler.start()
			return jsonify({"status": "ok", "message": "Scheduler started"})
		except SchedulerAlreadyRunningError:
			return jsonify({"status": "ok", "message": "Scheduler already running"})

	@app.route("/api/changes")
	def api_changes():
		days = int(request.args.get("days", 7))
		account = request.args.get("account")
		limit_param = request.args.get("limit")
		limit = None
		if limit_param is not None:
			try:
				limit = max(1, min(int(limit_param), 1000))
			except ValueError:
				limit = None
		data = report_provider.recent_changes(days=days, target_account=account, limit=limit)
		return jsonify(data)

	@app.route("/api/daily")
	def api_daily():
		days = int(request.args.get("days", 7))
		account = request.args.get("account")
		data = report_provider.daily_summary(days=days, target_account=account)
		return jsonify(data)

	@app.route("/export.csv")
	def export_csv():
		account = request.args.get("account")
		accounts = settings.target_accounts
		default_account = account or (accounts[0] if accounts else None)
		timeframes = [7, 14, 30]
		try:
			days = int(request.args.get("days", timeframes[0]))
		except (TypeError, ValueError):
			days = timeframes[0]
		if days not in timeframes:
			days = timeframes[0]

		records = report_provider.recent_changes(days=days, target_account=default_account)
		fieldnames = ["detected_at", "target_account", "list_type", "change_type", "username", "full_name"]
		buffer = io.StringIO()
		writer = csv.DictWriter(buffer, fieldnames=fieldnames)
		writer.writeheader()
		for record in records:
			writer.writerow(record)

		filename_account = default_account or "all"
		response = Response(buffer.getvalue(), mimetype="text/csv")
		response.headers["Content-Disposition"] = (
			f"attachment; filename=instatrack_changes_{filename_account}_{days}d.csv"
		)
		return response

	return app
