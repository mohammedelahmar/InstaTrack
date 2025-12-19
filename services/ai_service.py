"""IA-powered assistant for InstaTrack analytics."""

from __future__ import annotations

import importlib
import json
import re
from typing import Any, Callable, Dict, List, Optional

import google.generativeai as genai  # type: ignore[import]

try:  # pragma: no cover - optional typing aid when google.api_core is available
	google_exceptions = importlib.import_module("google.api_core.exceptions")
except Exception:  # pragma: no cover - fallback when dependency layout changes
	class _GoogleExceptionStub:  # type: ignore[too-few-public-methods]
		class NotFound(Exception):
			pass

	google_exceptions = _GoogleExceptionStub()  # type: ignore[misc]

from config.settings import settings
from utils.logger import get_logger
from utils.storage import MongoStorage, storage as default_storage
from services.report_service import ReportService, report_service as default_report_service


logger = get_logger(__name__)


class AIChatError(RuntimeError):
	"""Raised when the AI assistant cannot satisfy a request."""


class AIChatService:
	"""Bridge between InstaTrack data and the Gemini API."""

	def __init__(
		self,
		*,
		storage: MongoStorage | None = None,
		reports: ReportService | None = None,
		api_key: Optional[str] = None,
		model_name: Optional[str] = None,
		model_factory: Callable[[str], genai.GenerativeModel] | None = None,
	) -> None:
		self._storage = storage or default_storage
		self._reports = reports or default_report_service
		self._api_key = api_key or settings.gemini_api_key
		self._model_name = model_name or settings.gemini_model_name
		self._max_output_tokens = settings.gemini_max_output_tokens
		self._temperature = settings.gemini_temperature
		self._model_factory = model_factory
		self._model: genai.GenerativeModel | None = None
		self._configured = False

	def answer_question(self, *, target_account: Optional[str], question: str) -> Dict[str, object]:
		if not question or not question.strip():
			raise AIChatError("La question est obligatoire.")
		if not target_account:
			raise AIChatError("Sélectionnez un compte avant d'interroger l'assistant.")

		followers_snapshot = self._storage.latest_snapshot(target_account, "followers")
		following_snapshot = self._storage.latest_snapshot(target_account, "following")

		followers = followers_snapshot.get("users", []) if followers_snapshot else []
		following = following_snapshot.get("users", []) if following_snapshot else []

		if not followers and not following:
			raise AIChatError("Aucune donnée disponible pour ce compte. Lancez d'abord une capture.")

		followers_payload = [self._sanitize_user(user) for user in followers]
		following_payload = [self._sanitize_user(user) for user in following]

		relationships = self._reports.relationship_breakdown(target_account=target_account, limit=100)

		dataset = {
			"target_account": target_account,
			"followers": followers_payload,
			"following": following_payload,
			"statistics": {
				"followers_total": relationships.get("followers_total", len(followers_payload)),
				"following_total": relationships.get("following_total", len(following_payload)),
				"mutual_total": relationships.get("mutual_total", 0),
				"only_followers_total": relationships.get("only_followers_total", 0),
				"only_following_total": relationships.get("only_following_total", 0),
				"mutual_ratio": relationships.get("mutual_ratio", 0),
			},
		}

		local_answer = self._answer_builtin_question(
			question=question,
			followers=followers_payload,
			following=following_payload,
		)
		if local_answer:
			return {
				"answer": local_answer,
				"usage": {"prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0},
				"context": {
					"followers_count": len(followers_payload),
					"following_count": len(following_payload),
				},
			}

		answer, token_usage = self._call_model(question.strip(), dataset)

		return {
			"answer": answer,
			"usage": token_usage,
			"context": {
				"followers_count": len(followers_payload),
				"following_count": len(following_payload),
			},
		}

	def _call_model(self, question: str, dataset: Dict[str, object]) -> tuple[str, Dict[str, int]]:
		dataset_json = json.dumps(dataset, ensure_ascii=False)
		system_prompt = (
			"Tu es un analyste Instagram pour InstaTrack. Réponds en français, de façon concise,"
			" en citant des chiffres quand c'est pertinent, et rappelle tes limites si la question"
			" sort du périmètre des données fournies. Utilise uniquement les informations"
			" contenues dans le JSON suivant."
		)
		full_prompt = f"{system_prompt}\n\nQuestion: {question}\n\nDonnées: {dataset_json}"

		last_error: Exception | None = None
		not_found_error = False

		for candidate in self._model_candidates():
			try:
				model = self._ensure_model(candidate)
				response = model.generate_content(
					full_prompt,
					generation_config=genai.types.GenerationConfig(
						max_output_tokens=self._max_output_tokens,
						temperature=self._temperature,
					),
				)
			except google_exceptions.NotFound as exc:  # pragma: no cover - API specific failure
				not_found_error = True
				last_error = exc
				logger.warning("Modèle Gemini '%s' indisponible (%s). Tentative avec un modèle de repli.", candidate, exc)
				self._model = None
				continue
			except Exception as exc:  # pragma: no cover - network errors
				last_error = exc
				not_found_error = False
				logger.error("Gemini API call failed: %s", exc)
				break

			text, safety_message = self._resolve_response_text(response)
			if not text:
				text = safety_message or "Je n'ai pas pu générer de réponse. Reformulez votre question."

			usage = {}
			if hasattr(response, "usage_metadata") and response.usage_metadata:
				usage = {
					"prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
					"response_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
					"total_tokens": getattr(response.usage_metadata, "total_token_count", 0),
				}

			return text, usage

		if not_found_error:
			raise AIChatError(
				"Le modèle Gemini demandé est indisponible. Essayez gemini-1.5-flash-latest ou ajustez GEMINI_MODEL_NAME."
			) from last_error

		raise AIChatError("Impossible de contacter l'API Gemini. Vérifiez votre clé et réessayez.") from last_error

	def _ensure_model(self, model_name: Optional[str] = None) -> genai.GenerativeModel:
		if model_name and model_name != self._model_name:
			self._model_name = model_name
			self._model = None
		if not self._api_key:
			raise AIChatError("Configurez GEMINI_API_KEY dans votre environnement pour activer l'assistant IA.")
		if not self._configured:
			genai.configure(api_key=self._api_key)
			self._configured = True
		if self._model is None:
			factory = self._model_factory or (lambda name: genai.GenerativeModel(name))
			self._model = factory(self._model_name)
		return self._model  # type: ignore[return-value]

	def _model_candidates(self) -> List[str]:
		candidates: List[str] = []
		primary = (self._model_name or "").strip() or "gemini-1.5-flash-latest"
		self._add_model_aliases(candidates, primary)
		for fallback in [
			"gemini-1.5-flash-latest",
			"gemini-1.5-flash",
			"gemini-1.5-pro-latest",
			"gemini-pro",
		]:
			self._add_model_aliases(candidates, fallback)
		return candidates

	@staticmethod
	def _add_model_aliases(target: List[str], model_name: str) -> None:
		name = model_name.strip()
		if not name:
			return
		if name not in target:
			target.append(name)
		if name.startswith("models/"):
			alias = name.removeprefix("models/")
			if alias and alias not in target:
				target.append(alias)
		else:
			prefixed = f"models/{name}"
			if prefixed not in target:
				target.append(prefixed)

	def _answer_builtin_question(
		self,
		*,
		question: str,
		followers: List[Dict[str, object]],
		following: List[Dict[str, object]],
	) -> Optional[str]:
		normalized = question.lower()
		relations = self._build_relation_sets(followers, following)

		if any(phrase in normalized for phrase in ["who dont follow", "who don't follow", "who doesnt follow", "qui ne suivent pas"]):
			return self._format_followback_answer(relations)
		if "dont follow" in normalized and "how many" in normalized:
			count = len(relations["not_following_back"])
			return (
				f"{count} comptes suivis par l'utilisateur ne le suivent pas en retour."
				" Liste partielle : "
				+ self._format_user_list(relations["not_following_back"])
			)

		search_term = self._extract_search_term(question)
		if search_term:
			which_list = self._select_user_list_for_search(normalized)
			users = relations[which_list]
			matches = [
				user
				for user in users
				if self._matches_term(user, search_term)
			]
			if "how many" in normalized:
				return self._format_count_answer(search_term, matches, which_list)
			return self._format_search_answer(search_term, matches, which_list)

		if "any girls" in normalized or normalized.strip().endswith("girl"):
			matches = [user for user in followers if self._matches_term(user, "girl")]
			return self._format_search_answer("girl", matches, "followers")

		if "who follow him back" in normalized:
			mutual = relations["mutual"]
			return "Voici les followers qui se suivent mutuellement : " + self._format_user_list(mutual)

		return None

	@staticmethod
	def _build_relation_sets(
		followers: List[Dict[str, object]],
		following: List[Dict[str, object]],
	) -> Dict[str, List[Dict[str, object]]]:
		followers_map = {
			str(user.get("username", "")).lower(): user
			for user in followers
			if user.get("username")
		}
		following_map = {
			str(user.get("username", "")).lower(): user
			for user in following
			if user.get("username")
		}
		mutual = [user for key, user in followers_map.items() if key in following_map]
		not_following_back = [
			user
			for key, user in following_map.items()
			if key not in followers_map
		]
		followers_only = [
			user
			for key, user in followers_map.items()
			if key not in following_map
		]
		return {
			"followers": followers,
			"following": following,
			"mutual": mutual,
			"not_following_back": not_following_back,
			"followers_only": followers_only,
		}

	def _format_followback_answer(self, relations: Dict[str, List[Dict[str, object]]]) -> str:
		missing = relations["not_following_back"]
		if not missing:
			return "Tout le monde vous suit en retour 🎉"
		return (
			f"{len(missing)} comptes suivis ne suivent pas en retour : "
			+ self._format_user_list(missing)
		)

	def _format_user_list(self, users: List[Dict[str, object]], limit: int = 15) -> str:
		if not users:
			return "aucun"
		names = [self._display_name(user) for user in users[:limit]]
		extra = ""
		if len(users) > limit:
			extra = f" (+{len(users) - limit} autres)"
		return ", ".join(names) + extra

	@staticmethod
	def _display_name(user: Dict[str, object]) -> str:
		return str(user.get("username") or user.get("full_name") or "Utilisateur inconnu")

	@staticmethod
	def _extract_search_term(question: str) -> Optional[str]:
		match = re.search(r"['\"]([^'\"]+)['\"]", question)
		if match:
			return match.group(1).strip()
		match = re.search(r":\s*([\w\.\-@]+)$", question)
		if match:
			return match.group(1).strip()
		candidate = question.strip().split(" ")[-1]
		candidate = re.sub(r"[^\w@._-]", "", candidate)
		return candidate or None

	@staticmethod
	def _select_user_list_for_search(normalized_question: str) -> str:
		if "following" in normalized_question or "suit" in normalized_question:
			return "following"
		return "followers"

	@staticmethod
	def _matches_term(user: Dict[str, object], term: str) -> bool:
		needle = term.lower()
		return any(
			needle in str(value).lower()
			for value in [user.get("username", ""), user.get("full_name", "")]
		)

	def _format_search_answer(self, term: str, matches: List[Dict[str, object]], which_list: str) -> str:
		if not matches:
			return f"Aucun {which_list[:-1]} ne correspond à '{term}'."
		return (
			f"{len(matches)} {which_list} correspondent à '{term}' : "
			+ self._format_user_list(matches)
		)

	def _format_count_answer(self, term: str, matches: List[Dict[str, object]], which_list: str) -> str:
		count = len(matches)
		if not count:
			return f"Aucun {which_list[:-1]} ne contient '{term}'."
		return f"{count} {which_list} contiennent '{term}'."

	def _resolve_response_text(self, response: Any) -> tuple[str, Optional[str]]:
		if not response:
			return "", None
		try:
			text = (response.text or "").strip()
			if text:
				return text, None
		except ValueError as exc:  # Safety block typically triggers this
			reason = self._describe_safety_block(response, str(exc))
			logger.warning("Gemini response blocked: %s", reason)
			return "", reason

		for candidate_text in self._iter_candidate_texts(response):
			if candidate_text:
				return candidate_text, None

		return "", self._describe_safety_block(response, None)

	@staticmethod
	def _iter_candidate_texts(response: Any):
		candidates = getattr(response, "candidates", None) or []
		for candidate in candidates:
			content = getattr(candidate, "content", None)
			parts = getattr(content, "parts", None) if content else None
			if not parts:
				continue
			for part in parts:
				value = getattr(part, "text", None) or getattr(part, "raw", None)
				if value:
					yield str(value).strip()

	@staticmethod
	def _describe_safety_block(response: Any, error_message: Optional[str]) -> Optional[str]:
		reasons: List[str] = []
		candidates = getattr(response, "candidates", None) or []
		for candidate in candidates:
			finish_reason = getattr(candidate, "finish_reason", None)
			if finish_reason and finish_reason not in {"STOP", "UNKNOWN"}:
				reasons.append(str(finish_reason))
			for rating in getattr(candidate, "safety_ratings", None) or []:
				category = getattr(rating, "category", None)
				blocked = getattr(rating, "blocked", False)
				if blocked and category:
					reasons.append(str(category))
				elif blocked:
					reasons.append("contenu restreint")
		if error_message:
			reasons.append(error_message)
		if not reasons:
			return None
		unique = ", ".join(sorted(set(reasons)))
		return f"Réponse bloquée par Gemini (motifs: {unique}). Reformulez votre question."

	@staticmethod
	def _sanitize_user(user: Dict[str, object]) -> Dict[str, object]:
		return {
			"pk": user.get("pk"),
			"username": user.get("username"),
			"full_name": user.get("full_name"),
			"is_private": user.get("is_private"),
		}


def _build_default_service() -> AIChatService:
	return AIChatService()


ai_chat_service = _build_default_service()
