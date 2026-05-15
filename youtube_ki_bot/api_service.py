import json
from pathlib import Path
from typing import Optional

from youtube_ki_bot.app_models import GenerationRequest, RetrievalRequest
from youtube_ki_bot.database import DatabaseClient
from youtube_ki_bot.database_generation_repository import DatabaseGenerationRepository
from youtube_ki_bot.database_reference_repository import DatabaseReferenceRepository
from youtube_ki_bot.embedding_service import EmbeddingService
from youtube_ki_bot.generation_service import ScriptGenerationService
from youtube_ki_bot.reference_repository import ReferenceRepository
from youtube_ki_bot.retrieval_service import RetrievalService
from youtube_ki_bot.storage import CsvJsonStorage
from youtube_ki_bot.settings import ensure_directory
from youtube_ki_bot.text_utils import normalize_for_matching


class ApiService:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self._references = None
        self._embedding_index = None
        self._options = None
        self.database_client = DatabaseClient(config.database_url)
        self.database_repository = DatabaseReferenceRepository(self.database_client)
        self.generation_repository = DatabaseGenerationRepository(self.database_client)
        if self.database_repository.is_configured():
            self.database_repository.ensure_multi_database_support()

    def _should_use_database(self) -> bool:
        return self.database_repository.is_configured()

    def _load_reference_library(self, database_id: Optional[str] = None) -> list:
        self._validate_database_id(database_id)
        if database_id:
            if self._should_use_database():
                return self.database_repository.load_references(database_id=database_id)
            return []

        if self._references is not None:
            return self._references

        if self._should_use_database():
            references = self.database_repository.load_references()
            if references:
                self._references = references
                return self._references

        if self.paths.reference_library_path.exists():
            payload = json.loads(self.paths.reference_library_path.read_text(encoding="utf-8"))
            self._references = payload.get("references", [])
            return self._references

        repository = ReferenceRepository(
            self.paths.analysis_csv_path,
            self.paths.top_references_csv_path,
        )
        self._references = repository.build_reference_library()
        return self._references

    def _load_embedding_index(self, database_id: Optional[str] = None):
        self._validate_database_id(database_id)
        if database_id:
            if self._should_use_database():
                return self.database_repository.load_embedding_index(database_id=database_id)
            return None
        if self._embedding_index is not None:
            return self._embedding_index
        if self._should_use_database():
            embedding_index = self.database_repository.load_embedding_index()
            if embedding_index:
                self._embedding_index = embedding_index
                return self._embedding_index
        if not self.paths.embedding_index_path.exists():
            return None
        self._embedding_index = json.loads(
            self.paths.embedding_index_path.read_text(encoding="utf-8")
        )
        return self._embedding_index

    def get_options(self) -> dict:
        if self._options is not None:
            return self._options

        if self._should_use_database():
            options = self.database_repository.load_option_values()
            if all(options.values()):
                self._options = options
                return self._options

        self._options = {
            "platform_examples": [
                "nintendo_3ds",
                "nintendo_wii",
                "nintendo_switch",
                "playstation_psp",
                "playstation_ps3",
                "playstation_ps2",
            ],
            "format_examples": [
                "tutorial_guide",
                "technical_modding",
                "order_packaging",
                "buying_advice",
                "retro_nostalgia",
                "opinion_hot_take",
            ],
            "hook_examples": [
                "question_hook",
                "controversy_hook",
                "problem_solution",
                "direct_address",
                "customer_story",
            ],
        }
        return self._options

    def _build_retrieval_service(self) -> RetrievalService:
        return RetrievalService(
            EmbeddingService(
                api_key=self.config.openai_api_key,
                model=self.config.embedding_model,
            )
        )

    def retrieve_references(self, request: RetrievalRequest) -> list:
        references = self._load_reference_library(request.database_id)
        retrieval_service = self._build_retrieval_service()
        return retrieval_service.retrieve(
            references=references,
            query_text=request.query_text,
            platform=request.platform,
            format_label=request.format_label,
            hook_label=request.hook_label,
            top_k=request.top_k,
            embedding_index=self._load_embedding_index(request.database_id),
        )

    def list_references(
        self,
        database_id: Optional[str] = None,
        platform: Optional[str] = None,
        format_label: Optional[str] = None,
        hook_label: Optional[str] = None,
        q: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        references = self._load_reference_library(database_id)
        filtered = []
        normalized_query = normalize_for_matching(q) if q else ""

        for reference in references:
            if platform and platform not in reference.get("platform_labels", []):
                continue
            if format_label and format_label not in reference.get("format_labels", []):
                continue
            if hook_label and hook_label not in reference.get("hook_labels", []):
                continue
            if normalized_query and not self._reference_matches_query(reference, normalized_query):
                continue
            filtered.append(reference)

        filtered.sort(
            key=lambda item: (
                item.get("views") or 0,
                item.get("published_at") or "",
            ),
            reverse=True,
        )

        paginated = filtered[offset: offset + limit]
        return {
            "references": [self._serialize_reference(reference) for reference in paginated],
            "total": len(filtered),
        }

    def get_reference(self, reference_id: str, database_id: Optional[str] = None) -> Optional[dict]:
        references = self._load_reference_library(database_id)
        for reference in references:
            if str(reference.get("video_id")) == str(reference_id):
                return self._serialize_reference(reference)
        return None

    def list_databases(self) -> list[dict]:
        self._require_database()
        return self.database_repository.list_databases()

    def list_tables(self) -> list[dict]:
        self._require_database()
        return self.database_repository.list_tables()

    def get_table_rows(self, schema: str, name: str, limit: int, offset: int) -> dict:
        self._require_database()
        return self.database_repository.get_table_rows(schema, name, limit, offset)

    def insert_table_row(self, schema: str, name: str, data: dict) -> dict:
        self._require_database()
        return self.database_repository.insert_table_row(schema, name, data)

    def update_table_rows(self, schema: str, name: str, match: dict, data: dict) -> dict:
        self._require_database()
        return self.database_repository.update_table_rows(schema, name, match, data)

    def delete_table_rows(self, schema: str, name: str, match: dict) -> dict:
        self._require_database()
        return self.database_repository.delete_table_rows(schema, name, match)

    def get_database(self, database_id: str) -> Optional[dict]:
        self._require_database()
        return self.database_repository.get_database(database_id)

    def create_database(self, database_id: str, name: str, description: Optional[str] = None) -> dict:
        self._require_database()
        return self.database_repository.create_database(database_id, name, description)

    def delete_database(self, database_id: str) -> bool:
        self._require_database()
        return self.database_repository.delete_database(database_id)

    def _require_database(self) -> None:
        if not self.database_repository.is_configured():
            raise ValueError("DATABASE_URL fehlt. Multi-Datenbank-Endpunkte sind nicht verfügbar.")

    def _validate_database_id(self, database_id: Optional[str]) -> None:
        if database_id and self._should_use_database():
            if not self.database_repository.database_exists(database_id):
                raise LookupError("Database not found")

    @staticmethod
    def _reference_matches_query(reference: dict, normalized_query: str) -> bool:
        haystack = normalize_for_matching(
            " ".join(
                [
                    reference.get("title", ""),
                    reference.get("hook_text", ""),
                    reference.get("description", "") or "",
                    reference.get("channel", "") or "",
                ]
            )
        )
        return normalized_query in haystack

    @staticmethod
    def _serialize_reference(reference: dict) -> dict:
        return {
            "id": reference.get("video_id"),
            "title": reference.get("title", ""),
            "channel": reference.get("channel"),
            "youtube_url": reference.get("url"),
            "views": reference.get("views"),
            "duration_seconds": reference.get("duration_seconds"),
            "published_at": reference.get("published_at") or None,
            "platform_labels": list(reference.get("platform_labels", [])),
            "format_labels": list(reference.get("format_labels", [])),
            "hook_labels": list(reference.get("hook_labels", [])),
            "hook_text": reference.get("hook_text") or None,
            "description": reference.get("description"),
            "transcript": reference.get("transcript_text") or None,
        }

    def generate_script(self, request: GenerationRequest) -> tuple[dict, list, Path]:
        if not self.config.openai_api_key:
            raise ValueError("OPENAI_API_KEY fehlt. Script-Generierung ist nicht verfügbar.")

        retrieval_request = RetrievalRequest.from_generation_request(request)
        retrieval_results = self.retrieve_references(retrieval_request)

        generator = ScriptGenerationService(
            api_key=self.config.openai_api_key,
            model=self.config.generation_model,
        )
        payload = generator.generate_script(
            brief=request.to_prompt_brief(),
            retrieval_results=retrieval_results,
            platform=request.platform,
            format_label=request.format_label,
            hook_label=request.hook_label,
        )
        output_path = None
        if self.config.persist_generated_scripts:
            output_path = self._save_generated_script(request, payload, retrieval_results)
            self._persist_generated_script(
                request=request,
                retrieval_request=retrieval_request,
                retrieval_results=retrieval_results,
                payload=payload,
                model=generator.model,
            )
        return payload, retrieval_results, output_path

    def _save_generated_script(self, request: GenerationRequest, payload: dict, retrieval_results: list) -> Path:
        ensure_directory(self.paths.generated_scripts_dir)
        from datetime import datetime
        import re

        def slugify_filename(text, max_length=60):
            normalized = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß\\s-]", "", text).strip().lower()
            normalized = normalized.replace("ß", "ss")
            normalized = re.sub(r"\\s+", "-", normalized)
            normalized = re.sub(r"-+", "-", normalized).strip("-")
            return normalized[:max_length] or "script"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title_seed = payload.get("title_ideas", [request.topic])[0] if payload.get("title_ideas") else request.topic
        output_path = self.paths.generated_scripts_dir / f"{timestamp}_{slugify_filename(title_seed)}.json"
        output_payload = {
            "created_at": datetime.now().isoformat(),
            "request": request.to_dict(),
            "script_payload": payload,
            "references_used": [
                {
                    "score": item["score"],
                    "metadata_score": item["metadata_score"],
                    "keyword_score": item["keyword_score"],
                    "semantic_score": item["semantic_score"],
                    "performance_score": item["performance_score"],
                    "video_id": item["reference"]["video_id"],
                    "title": item["reference"]["title"],
                    "url": item["reference"]["url"],
                    "platform_labels": item["reference"]["platform_labels"],
                    "format_labels": item["reference"]["format_labels"],
                    "hook_labels": item["reference"]["hook_labels"],
                }
                for item in retrieval_results
            ],
        }
        CsvJsonStorage().save_json(output_payload, output_path)
        return output_path

    def _persist_generated_script(
        self,
        request: GenerationRequest,
        retrieval_request: RetrievalRequest,
        retrieval_results: list,
        payload: dict,
        model: str,
    ) -> None:
        if not self.generation_repository.is_configured():
            return
        self.generation_repository.persist_generation(
            request=request,
            retrieval_request=retrieval_request.to_dict(),
            retrieval_results=retrieval_results,
            payload=payload,
            model=model,
        )
