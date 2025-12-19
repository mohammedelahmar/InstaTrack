import os
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

os.environ["USE_MOCK_DB"] = "1"

from services.ai_service import AIChatService, AIChatError
from services.report_service import ReportService
from utils.storage import MongoStorage


class DummyModel:
	def __init__(self, reply="Réponse factice") -> None:
		self.reply = reply
		self.prompts: list[str] = []

	def generate_content(self, prompt, generation_config=None):
		self.prompts.append(prompt)
		return SimpleNamespace(
			text=self.reply,
			usage_metadata=SimpleNamespace(
				prompt_token_count=42,
				candidates_token_count=21,
				total_token_count=63,
			),
		)


class BlockedResponse:
	def __init__(self) -> None:
		self.usage_metadata = None
		self.candidates = [
			SimpleNamespace(
				finish_reason="SAFETY",
				safety_ratings=[SimpleNamespace(category="HATE", blocked=True)],
				content=SimpleNamespace(parts=[]),
			)
		]

	@property
	def text(self):
		raise ValueError("blocked by safety")


def test_ai_chat_service_returns_answer_with_stub_model():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	collected_at = datetime(2025, 8, 1, 10, tzinfo=UTC)

	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 1, "username": "alice", "full_name": "Alice"}],
		collected_at=collected_at,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="following",
		users=[{"pk": 2, "username": "bob", "full_name": "Bob"}],
		collected_at=collected_at,
	)

	dummy_model = DummyModel()
	service = AIChatService(
		storage=storage,
		reports=report,
		api_key="fake-key",
		model_factory=lambda _: dummy_model,
	)

	result = service.answer_question(target_account="demo", question="Combien de followers ?")

	assert result["answer"] == dummy_model.reply
	assert result["usage"]["total_tokens"] == 63
	assert dummy_model.prompts, "The prompt should be sent to the dummy model"
	assert "alice" in dummy_model.prompts[0]
	assert "bob" in dummy_model.prompts[0]


def test_ai_chat_service_requires_data():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	service = AIChatService(storage=storage, reports=report, api_key="fake", model_factory=lambda _: DummyModel())

	try:
		service.answer_question(target_account="demo", question="Hello")
	except AIChatError as exc:
		assert "Aucune donnée" in str(exc)
	else:
		assert False, "AIChatError devait être levée lorsque aucune donnée n'est disponible"


def test_ai_chat_service_handles_blocked_response_message():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	collected_at = datetime(2025, 8, 1, 10, tzinfo=UTC)
	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[{"pk": 1, "username": "alice", "full_name": "Alice"}],
		collected_at=collected_at,
	)
	blocked_response = BlockedResponse()

	class BlockedModel:
		def generate_content(self, *_args, **_kwargs):
			return blocked_response

	service = AIChatService(
		storage=storage,
		reports=report,
		api_key="fake",
		model_factory=lambda _name: BlockedModel(),
	)

	result = service.answer_question(target_account="demo", question="Question sensible ?")
	assert "Réponse bloquée par Gemini" in result["answer"]


def test_builtin_followback_answer_without_gemini():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	collected_at = datetime(2025, 8, 1, 10, tzinfo=UTC)
	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[
			{"pk": 1, "username": "alice", "full_name": "Alice"},
			{"pk": 2, "username": "bob", "full_name": "Bob"},
		],
		collected_at=collected_at,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="following",
		users=[
			{"pk": 3, "username": "alice", "full_name": "Alice"},
			{"pk": 4, "username": "carol", "full_name": "Carol"},
		],
		collected_at=collected_at,
	)

	def _fail_model(_name):  # pragma: no cover - should never be called
		pytest.fail("Gemini ne doit pas être appelé pour les questions locales")

	service = AIChatService(
		storage=storage,
		reports=report,
		api_key="fake",
		model_factory=_fail_model,
	)

	result = service.answer_question(target_account="demo", question="Who dont follow this account back ?")
	assert "carol" in result["answer"].lower()
	assert result["usage"]["total_tokens"] == 0


def test_builtin_search_answer_returns_matches():
	storage = MongoStorage()
	report = ReportService(storage=storage)
	collected_at = datetime(2025, 8, 1, 10, tzinfo=UTC)
	storage.store_snapshot(
		target_account="demo",
		list_type="followers",
		users=[
			{"pk": 1, "username": "zay__een__ab", "full_name": "Zaynab"},
			{"pk": 2, "username": "mike", "full_name": "Mike"},
		],
		collected_at=collected_at,
	)
	storage.store_snapshot(
		target_account="demo",
		list_type="following",
		users=[],
		collected_at=collected_at,
	)

	service = AIChatService(
		storage=storage,
		reports=report,
		api_key="fake",
		model_factory=lambda name: DummyModel(),
	)

	result = service.answer_question(target_account="demo", question="Search for followers like : zaynab")
	assert "zaynab" in result["answer"].lower()
