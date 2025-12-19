"""Application configuration management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import List

import os

from dotenv import load_dotenv


def _load_env() -> None:
	"""Load environment variables from the first .env file that exists."""

	candidates = [
		Path(__file__).resolve().parent.parent / ".env",
		Path(__file__).resolve().parent / ".env",
		Path.cwd() / ".env",
	]

	loaded = False
	for env_path in candidates:
		if env_path.exists():
			load_dotenv(dotenv_path=env_path, override=False)
			loaded = True

	if not loaded:
		load_dotenv()


def _env_bool(key: str, default: bool = False) -> bool:
	value = os.getenv(key)
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(key: str, default: str = "") -> List[str]:
	raw = os.getenv(key, default)
	return [item.strip() for item in raw.split(",") if item.strip()]


_load_env()


@dataclass(slots=True)
class Settings:
	"""Centralised application settings loaded from environment variables."""

	mongo_uri: str = field(default_factory=lambda: os.getenv("MONGO_URI", "mongodb://localhost:27017"))
	mongo_db: str = field(default_factory=lambda: os.getenv("MONGO_DB_NAME", "instatrack"))
	mongo_snapshots_collection: str = field(default="snapshots")
	mongo_changes_collection: str = field(default="changes")

	instagram_username: str | None = field(default_factory=lambda: os.getenv("INSTAGRAM_USERNAME"))
	instagram_password: str | None = field(default_factory=lambda: os.getenv("INSTAGRAM_PASSWORD"))
	# Optional: provide an Instagram sessionid cookie to avoid interactive challenges
	instagram_sessionid: str | None = field(default_factory=lambda: os.getenv("INSTAGRAM_SESSIONID"))
	instagram_session_path: Path = field(
		default_factory=lambda: Path(os.getenv("INSTAGRAM_SESSION_PATH", "data/cache/insta_session.json"))
	)
	instagram_disable_session: bool = field(default_factory=lambda: _env_bool("INSTAGRAM_DISABLE_SESSION"))

	target_accounts: List[str] = field(default_factory=lambda: _env_list("TARGET_ACCOUNTS"))

	gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
	gemini_model_name: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash-latest"))
	gemini_max_output_tokens: int = field(default_factory=lambda: int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "512")))
	gemini_temperature: float = field(default_factory=lambda: float(os.getenv("GEMINI_TEMPERATURE", "0.4")))

	scrape_hour_utc: int = field(default_factory=lambda: int(os.getenv("SCRAPE_HOUR_UTC", "3")))
	scrape_minute_utc: int = field(default_factory=lambda: int(os.getenv("SCRAPE_MINUTE_UTC", "0")))

	dashboard_auto_refresh_seconds: int = field(
		default_factory=lambda: int(os.getenv("AUTO_REFRESH_INTERVAL_SECONDS", "0"))
	)

	min_request_delay: float = field(default_factory=lambda: float(os.getenv("MIN_REQUEST_DELAY", "2.5")))
	max_request_delay: float = field(default_factory=lambda: float(os.getenv("MAX_REQUEST_DELAY", "5.0")))
	max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
	retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("RETRY_BACKOFF_SECONDS", "30")))

	use_mock_db: bool = field(default_factory=lambda: _env_bool("USE_MOCK_DB"))

	log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
	log_directory: Path = field(default_factory=lambda: Path(os.getenv("LOG_DIR", "data/logs")))

	@property
	def scrape_time(self) -> time:
		return time(hour=self.scrape_hour_utc, minute=self.scrape_minute_utc)

	def ensure_directories(self) -> None:
		"""Create directories required for runtime assets."""

		self.instagram_session_path.parent.mkdir(parents=True, exist_ok=True)
		self.log_directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
