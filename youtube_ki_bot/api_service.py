import json
from pathlib import Path

from youtube_ki_bot.app_models import GenerationRequest, RetrievalRequest
from youtube_ki_bot.embedding_service import EmbeddingService
from youtube_ki_bot.generation_service import ScriptGenerationService
from youtube_ki_bot.reference_repository import ReferenceRepository
from youtube_ki_bot.retrieval_service import RetrievalService
from youtube_ki_bot.storage import CsvJsonStorage
from youtube_ki_bot.settings import ensure_directory


class ApiService:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self._references = None
        self._embedding_index = None

    def _load_reference_library(self) -> list:
        if self._references is not None:
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

    def _load_embedding_index(self):
        if self._embedding_index is not None:
            return self._embedding_index
        if not self.paths.embedding_index_path.exists():
            return None
        self._embedding_index = json.loads(
            self.paths.embedding_index_path.read_text(encoding="utf-8")
        )
        return self._embedding_index

    def _build_retrieval_service(self) -> RetrievalService:
        return RetrievalService(
            EmbeddingService(
                api_key=self.config.openai_api_key,
                model=self.config.embedding_model,
            )
        )

    def retrieve_references(self, request: RetrievalRequest) -> list:
        references = self._load_reference_library()
        retrieval_service = self._build_retrieval_service()
        return retrieval_service.retrieve(
            references=references,
            query_text=request.query_text,
            platform=request.platform,
            format_label=request.format_label,
            hook_label=request.hook_label,
            top_k=request.top_k,
            embedding_index=self._load_embedding_index(),
        )

    def generate_script(self, request: GenerationRequest) -> tuple[dict, list, Path]:
        if not self.config.openai_api_key:
            raise ValueError("OPENAI_API_KEY fehlt. Script-Generierung ist nicht verfügbar.")

        retrieval_request = RetrievalRequest.from_generation_request(request)
        retrieval_results = self.retrieve_references(retrieval_request)

        generator = ScriptGenerationService(
            api_key=self.config.openai_api_key,
            model=self.config.generation_model,
        )
        output = generator.generate_script(
            brief=request.to_prompt_brief(),
            retrieval_results=retrieval_results,
            platform=request.platform,
            format_label=request.format_label,
            hook_label=request.hook_label,
        )
        payload = self._extract_json_payload(output)
        output_path = self._save_generated_script(request, payload, retrieval_results)
        return payload, retrieval_results, output_path

    @staticmethod
    def _extract_json_payload(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        return json.loads(cleaned)

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
