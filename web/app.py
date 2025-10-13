"""Flask application exposing InstaTrack dashboard."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from config.settings import settings
from services.report_service import ReportService, report_service as default_report_service


def create_app(reports: ReportService | None = None) -> Flask:
	app = Flask(__name__, static_folder="static", template_folder="templates")
	report_provider = reports or default_report_service

	@app.route("/")
	def dashboard():
		account = request.args.get("account")
		accounts = settings.target_accounts
		default_account = account or (accounts[0] if accounts else None)

		counts = report_provider.counts(target_account=default_account)
		changes = report_provider.recent_changes(target_account=default_account)
		daily = report_provider.daily_summary(target_account=default_account)

		return render_template(
			"dashboard.html",
			counts=counts,
			changes=changes,
			daily=daily,
			accounts=accounts,
			default_account=default_account,
		)

	@app.route("/api/changes")
	def api_changes():
		days = int(request.args.get("days", 7))
		account = request.args.get("account")
		data = report_provider.recent_changes(days=days, target_account=account)
		return jsonify(data)

	@app.route("/api/daily")
	def api_daily():
		days = int(request.args.get("days", 7))
		account = request.args.get("account")
		data = report_provider.daily_summary(days=days, target_account=account)
		return jsonify(data)

	return app
