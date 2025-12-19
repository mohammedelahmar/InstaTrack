"""Utilities for reading and writing the InstaTrack environment file."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import os

from dotenv import dotenv_values, set_key, unset_key


_ENV_CANDIDATES = [
	Path(__file__).resolve().parent.parent / ".env",
	Path(__file__).resolve().parent / ".env",
	Path.cwd() / ".env",
]


def _resolve_env_path() -> Path:
	for candidate in _ENV_CANDIDATES:
		if candidate.exists():
			return candidate
	default_path = _ENV_CANDIDATES[0]
	default_path.parent.mkdir(parents=True, exist_ok=True)
	default_path.touch(exist_ok=True)
	return default_path


class EnvStore:
	"""Persist configuration updates back to the .env file."""

	def __init__(self, path: Path | None = None) -> None:
		self._path = path or _resolve_env_path()
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._path.touch(exist_ok=True)

	@property
	def path(self) -> Path:
		return self._path

	def read(self) -> Dict[str, str]:
		return {key: value for key, value in dotenv_values(self._path).items() if value is not None}

	def set(self, key: str, value: str | None) -> None:
		if value is None or value == "":
			self.remove(key)
			return
		set_key(str(self._path), key, value, quote_mode="never")
		os.environ[key] = value

	def remove(self, key: str) -> None:
		unset_key(str(self._path), key)
		os.environ.pop(key, None)

	def update_many(self, mapping: Dict[str, str | None]) -> None:
		for key, value in mapping.items():
			self.set(key, value)
