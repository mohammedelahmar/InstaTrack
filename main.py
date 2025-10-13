"""Command-line entry point for InstaTrack."""

from __future__ import annotations

import argparse
import json

from config.settings import settings
from services.report_service import ReportService
from services.tracker_service import TrackerService
from utils.logger import get_logger
from utils.scheduler import TrackerScheduler
from web.app import create_app


logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="InstaTrack monitoring tool")
	subparsers = parser.add_subparsers(dest="command")

	subparsers.add_parser("run", help="Collect snapshots immediately")

	report_parser = subparsers.add_parser("report", help="Afficher les changements récents")
	report_parser.add_argument("--days", type=int, default=7, help="Fenêtre en jours (défaut: 7)")
	report_parser.add_argument("--account", help="Compte cible (défaut: premier de TARGET_ACCOUNTS)")
	report_parser.add_argument("--csv", help="Chemin d'export CSV optionnel")

	subparsers.add_parser("schedule", help="Lancer le suivi quotidien")

	web_parser = subparsers.add_parser("web", help="Démarrer l'interface Flask")
	web_parser.add_argument("--host", default="127.0.0.1")
	web_parser.add_argument("--port", type=int, default=5000)
	web_parser.add_argument("--debug", action="store_true")

	return parser


def main() -> None:
	parser = _build_parser()
	args = parser.parse_args()

	if not args.command:
		parser.print_help()
		return

	tracker = TrackerService()
	reports = ReportService()

	if args.command == "run":
		summaries = tracker.run_once()
		print(json.dumps(summaries, indent=2))
		return

	if args.command == "report":
		account = args.account or (settings.target_accounts[0] if settings.target_accounts else None)
		summary = reports.counts(days=args.days, target_account=account)
		changes = reports.recent_changes(days=args.days, target_account=account)
		print("Résumé :")
		for key, value in summary.items():
			print(f"  {key}: {value}")

		if args.csv:
			path = reports.export_changes_to_csv(args.csv, days=args.days, target_account=account)
			print(f"\nExport CSV créé: {path}")

		print("\nÉvénements :")
		for change in changes:
			print(
				f"  {change['detected_at']} | {change['list_type']} {change['change_type']} -> {change['username']}"
			)
		return

	if args.command == "schedule":
		scheduler = TrackerScheduler(tracker)
		scheduler.start()
		scheduler.block()
		return

	if args.command == "web":
		app = create_app(reports)
		app.run(host=args.host, port=args.port, debug=args.debug)
		return

	parser.print_help()


if __name__ == "__main__":  # pragma: no cover - manual execution
	main()
