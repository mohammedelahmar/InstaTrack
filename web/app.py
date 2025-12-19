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
from services.settings_service import (
	SettingsError,
	SettingsService,
	settings_service as default_settings_service,
)
from services.tracker_service import TrackerService, tracker_service as default_tracker_service
from utils.scheduler import TrackerScheduler
from services.ai_service import AIChatService, AIChatError, ai_chat_service as default_ai_chat_service

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


def create_app(
	reports: ReportService | None = None,
	tracker: TrackerService | None = None,
	settings_manager: SettingsService | None = None,
	ai_chat: AIChatService | None = None,
) -> Flask:
	app = Flask(__name__, static_folder="static", template_folder="templates")
	report_provider = reports or default_report_service
	tracker_provider = tracker or default_tracker_service
	settings_provider = settings_manager or default_settings_service
	ai_provider = ai_chat or default_ai_chat_service

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
		start_param = request.args.get("start")
		end_param = request.args.get("end")

		parsed_start = report_provider._parse_date(start_param) if start_param else None
		parsed_end = report_provider._parse_date(end_param, end_of_day=True) if end_param else None

		resolved_start, resolved_end = report_provider._resolve_range(
			days=days,
			start=start_param,
			end=end_param,
		)

		counts = report_provider.counts(
			days=days,
			start=start_param,
			end=end_param,
			target_account=default_account,
		)
		changes = report_provider.recent_changes(
			days=days,
			start=start_param,
			end=end_param,
			target_account=default_account,
			limit=change_limit,
		)
		daily = report_provider.daily_summary(
			days=days,
			start=start_param,
			end=end_param,
			target_account=default_account,
		)
		totals = report_provider.current_totals(target_account=default_account)
		insights = report_provider.insights(
			days=days,
			start=start_param,
			end=end_param,
			target_account=default_account,
		)
		gaps = report_provider.follow_back_gaps(target_account=default_account, limit=25)
		comparison = report_provider.compare_snapshots(
			target_account=default_account,
			start=start_param,
			end=end_param,
			limit=25,
		)
		history = report_provider.snapshot_history(
			target_account=default_account,
			start=start_param,
			end=end_param,
			limit=25,
		)
		relationships = report_provider.relationship_breakdown(
			target_account=default_account,
			limit=25,
		)

		range_context = {
			"start_iso": report_provider._iso_or_none(resolved_start),
			"end_iso": report_provider._iso_or_none(resolved_end),
			"start_date": parsed_start.date().isoformat() if parsed_start else "",
			"end_date": parsed_end.date().isoformat() if parsed_end else "",
		}

		return render_template(
			"dashboard.html",
			counts=counts,
			changes=changes,
			daily=daily,
			totals=totals,
			insights=insights,
			gaps=gaps,
			comparison=comparison,
			history=history,
			relationships=relationships,
			range_context=range_context,
			accounts=accounts,
			default_account=default_account,
			timeframes=timeframes,
			selected_days=days,
			selected_start=range_context["start_date"],
			selected_end=range_context["end_date"],
			change_limit=change_limit,
			auto_refresh_seconds=settings.dashboard_auto_refresh_seconds,
			ai_enabled=bool(settings.gemini_api_key),
		)

	@app.route("/settings")
	def settings_page():
		return render_template("settings.html", settings=settings_provider.settings_snapshot())

	@app.route("/api/settings", methods=["GET"])
	def api_settings_snapshot():
		return jsonify({"status": "ok", "settings": settings_provider.settings_snapshot()})

	@app.route("/api/settings/accounts", methods=["POST"])
	def api_add_account():
		payload = request.get_json(silent=True) or {}
		username = (payload.get("username") or "").strip()
		try:
			accounts = settings_provider.add_target_account(username)
			return jsonify({"status": "ok", "accounts": accounts})
		except SettingsError as exc:
			return jsonify({"status": "error", "message": str(exc)}), 400

	@app.route("/api/settings/accounts/<username>", methods=["DELETE"])
	def api_remove_account(username: str):
		try:
			accounts = settings_provider.remove_target_account(username)
			return jsonify({"status": "ok", "accounts": accounts})
		except SettingsError as exc:
			return jsonify({"status": "error", "message": str(exc)}), 400

	@app.route("/api/settings/account-check", methods=["POST"])
	def api_check_account():
		payload = request.get_json(silent=True) or {}
		username = (payload.get("username") or "").strip()
		try:
			privacy = settings_provider.check_account_privacy(username)
			return jsonify(
				{
					"status": "ok",
					"username": privacy.username,
					"full_name": privacy.full_name,
					"is_private": privacy.is_private,
					"is_verified": privacy.is_verified,
					"pk": privacy.pk,
				}
			)
		except SettingsError as exc:
			return jsonify({"status": "error", "message": str(exc)}), 400

	@app.route("/api/settings/follow-request", methods=["POST"])
	def api_follow_request():
		payload = request.get_json(silent=True) or {}
		username = (payload.get("username") or "").strip()
		add_after = bool(payload.get("add_to_targets"))
		try:
			result = settings_provider.send_follow_request(username)
			accounts = None
			if add_after:
				try:
					accounts = settings_provider.add_target_account(username)
				except SettingsError as add_error:
					if "déjà suivi" not in str(add_error):
						raise
					accounts = settings_provider.settings_snapshot()["target_accounts"]
			return jsonify({"status": "ok", "result": result, "accounts": accounts})
		except SettingsError as exc:
			return jsonify({"status": "error", "message": str(exc)}), 400

	@app.route("/api/settings/session", methods=["POST"])
	def api_session_update():
		payload = request.get_json(silent=True) or {}
		raw_value = payload.get("session_id")
		persist = bool(payload.get("persist", True))
		try:
			settings_provider.set_session_id(raw_value, persist=persist)
			return jsonify(
				{
					"status": "ok",
					"session_mask": settings_provider.settings_snapshot()["session_mask"],
					"persist": persist,
				}
			)
		except SettingsError as exc:
			return jsonify({"status": "error", "message": str(exc)}), 400

	@app.route("/api/settings/auto-refresh", methods=["POST"])
	def api_auto_refresh():
		payload = request.get_json(silent=True) or {}
		raw_seconds = payload.get("seconds", 0)
		try:
			seconds = int(raw_seconds)
		except (TypeError, ValueError):
			return jsonify({"status": "error", "message": "Valeur d'intervalle invalide."}), 400
		try:
			updated = settings_provider.set_auto_refresh_seconds(seconds)
			return jsonify({"status": "ok", "seconds": updated})
		except SettingsError as exc:
			return jsonify({"status": "error", "message": str(exc)}), 400

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
		start_param = request.args.get("start")
		end_param = request.args.get("end")

		counts = report_provider.counts(
			days=days,
			start=start_param,
			end=end_param,
			target_account=account,
		)
		insights = report_provider.insights(
			days=days,
			start=start_param,
			end=end_param,
			target_account=account,
		)
		recent = report_provider.recent_changes(
			days=days,
			start=start_param,
			end=end_param,
			target_account=account,
			limit=preview_limit,
		)
		totals = report_provider.current_totals(target_account=account)
		gaps = report_provider.follow_back_gaps(target_account=account, limit=preview_limit)
		comparison = report_provider.compare_snapshots(
			target_account=account,
			start=start_param,
			end=end_param,
			limit=preview_limit,
		)
		history = report_provider.snapshot_history(
			target_account=account,
			start=start_param,
			end=end_param,
			limit=preview_limit,
		)
		relationships = report_provider.relationship_breakdown(target_account=account, limit=preview_limit)
		return jsonify(
			{
				"status": "ok",
				"counts": counts,
				"insights": insights,
				"recent": recent,
				"totals": totals,
				"gaps": gaps,
				"comparison": comparison,
				"history": history,
				"relationships": relationships,
			}
		)

	@app.route("/api/relationships")
	def api_relationships():
		account = request.args.get("account") or None
		try:
			limit = int(request.args.get("limit", 50))
		except (TypeError, ValueError):
			limit = 50
		limit = max(1, min(limit, 500))
		breakdown = report_provider.relationship_breakdown(target_account=account, limit=limit)
		return jsonify({"status": "ok", "relationships": breakdown})

	@app.route("/api/ai/chat", methods=["POST"])
	def api_ai_chat():
		payload = request.get_json(silent=True) or {}
		account = (payload.get("account") or "").strip() or request.args.get("account") or None
		if not account and settings.target_accounts:
			account = settings.target_accounts[0]
		question = (payload.get("question") or "").strip()
		try:
			answer = ai_provider.answer_question(target_account=account, question=question)
			return jsonify({"status": "ok", **answer})
		except AIChatError as exc:
			return jsonify({"status": "error", "message": str(exc)}), 400
		except Exception as exc:  # pragma: no cover - defensive logging
			app.logger.exception("AI chat endpoint failed")
			return jsonify({"status": "error", "message": "Erreur interne lors de l'appel IA."}), 500

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
		start_param = request.args.get("start")
		end_param = request.args.get("end")
		data = report_provider.recent_changes(
			days=days,
			start=start_param,
			end=end_param,
			target_account=account,
			limit=limit,
		)
		return jsonify(data)

	@app.route("/api/daily")
	def api_daily():
		days = int(request.args.get("days", 7))
		account = request.args.get("account")
		start_param = request.args.get("start")
		end_param = request.args.get("end")
		data = report_provider.daily_summary(
			days=days,
			start=start_param,
			end=end_param,
			target_account=account,
		)
		return jsonify(data)

	@app.route("/api/snapshots")
	def api_snapshots():
		account = request.args.get("account") or None
		start_param = request.args.get("start")
		end_param = request.args.get("end")
		limit = int(request.args.get("limit", 50))
		limit = max(1, min(limit, 200))
		history = report_provider.snapshot_history(
			target_account=account,
			start=start_param,
			end=end_param,
			limit=limit,
		)
		return jsonify({"status": "ok", "history": history})

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
		start_param = request.args.get("start")
		end_param = request.args.get("end")

		records = report_provider.recent_changes(
			days=days,
			start=start_param,
			end=end_param,
			target_account=default_account,
		)
		fieldnames = ["detected_at", "target_account", "list_type", "change_type", "username", "full_name"]
		buffer = io.StringIO()
		writer = csv.DictWriter(buffer, fieldnames=fieldnames)
		writer.writeheader()
		for record in records:
			writer.writerow(record)

		filename_account = default_account or "all"
		date_suffix = ""
		if start_param or end_param:
			start_label_dt = report_provider._parse_date(start_param) if start_param else None
			end_label_dt = report_provider._parse_date(end_param, end_of_day=True) if end_param else None
			start_label = start_label_dt.date().isoformat().replace("-", "") if start_label_dt else ""
			end_label = end_label_dt.date().isoformat().replace("-", "") if end_label_dt else ""
			if start_label or end_label:
				date_suffix = f"_{start_label or 'start'}-{end_label or 'end'}"
		response = Response(buffer.getvalue(), mimetype="text/csv")
		response.headers["Content-Disposition"] = (
			f"attachment; filename=instatrack_changes_{filename_account}_{days}d{date_suffix}.csv"
		)
		return response

	return app
