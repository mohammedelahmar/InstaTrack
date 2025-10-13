"""Scheduling utilities for periodic snapshot collection."""

from __future__ import annotations

from datetime import datetime, time
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings
from services.tracker_service import TrackerService, tracker_service
from utils.logger import get_logger


logger = get_logger(__name__)


class TrackerScheduler:
	"""Wrap APScheduler to run the tracker once per day."""

	def __init__(self, service: TrackerService = tracker_service) -> None:
		self._service = service
		self._scheduler = BackgroundScheduler(timezone="UTC")
		self._stop_event = Event()

	def start(self) -> None:
		scrape_time: time = settings.scrape_time
		trigger = CronTrigger(hour=scrape_time.hour, minute=scrape_time.minute)
		self._scheduler.add_job(self._execute_job, trigger=trigger, id="daily_tracker", replace_existing=True)
		self._scheduler.start()
		logger.info(
			"Scheduled daily snapshot at %02d:%02d UTC for accounts: %s",
			scrape_time.hour,
			scrape_time.minute,
			", ".join(settings.target_accounts) or "<none>",
		)

	def _execute_job(self) -> None:
		logger.info("Running scheduled tracker job at %s", datetime.utcnow().isoformat())
		try:
			summaries = self._service.run_once()
			logger.info("Tracker job complete: %s", summaries)
		except Exception:
			logger.exception("Tracker job failed")

	def block(self) -> None:
		try:
			self._stop_event.wait()
		except KeyboardInterrupt:
			logger.info("Stopping scheduler via keyboard interrupt")
			self.stop()

	def stop(self) -> None:
		self._scheduler.shutdown(wait=False)
		self._stop_event.set()


tracker_scheduler = TrackerScheduler()
