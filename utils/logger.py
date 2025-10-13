"""Logging utilities for InstaTrack."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import settings


_LOG_FILE = settings.log_directory / "instatrack.log"


def _configure_root_logger() -> None:
	if logging.getLogger().handlers:
		return

	formatter = logging.Formatter(
		"%(asctime)s | %(name)s | %(levelname)s | %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S",
	)

	console_handler = logging.StreamHandler()
	console_handler.setFormatter(formatter)

	file_handler = RotatingFileHandler(_LOG_FILE, maxBytes=2_000_000, backupCount=3)
	file_handler.setFormatter(formatter)

	root = logging.getLogger()
	root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
	root.addHandler(console_handler)
	root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
	"""Return a configured logger for the provided module name."""

	_configure_root_logger()
	return logging.getLogger(name)
