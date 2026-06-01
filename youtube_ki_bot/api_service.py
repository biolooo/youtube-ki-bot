import json
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse
from collections import Counter
from datetime import datetime, timedelta, timezone

from youtube_ki_bot.app_models import GenerationRequest, RetrievalRequest
from youtube_ki_bot.database import DatabaseClient
from youtube_ki_bot.database_generation_repository import DatabaseGenerationRepository
from youtube_ki_bot.database_reference_repository import DatabaseReferenceRepository
from youtube_ki_bot.database_sync_repository import DatabaseSyncRepository
from youtube_ki_bot.embedding_service import EmbeddingService
from youtube_ki_bot.generation_service import ScriptGenerationService
from youtube_ki_bot.analysis_service import AnalysisService
from youtube_ki_bot.openai_text_service import OpenAITextService
from youtube_ki_bot.reference_repository import ReferenceRepository
from youtube_ki_bot.retrieval_service import RetrievalService
from youtube_ki_bot.settings import load_taxonomy
from youtube_ki_bot.storage import CsvJsonStorage
from youtube_ki_bot.taxonomy_service import TaxonomyClassifier
from youtube_ki_bot.settings import ensure_directory
from youtube_ki_bot.text_utils import extract_hook_text, normalize_for_matching, split_sentences
from youtube_ki_bot.transcript_service import TranscriptPipelineError, TranscriptService
from youtube_ki_bot.transcriptlol_service import TranscriptLolService
from youtube_ki_bot.youtube_service import YouTubeDataService


class ApiService:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self._references = None
        self._embedding_index = None
        self._options = None
        self.database_client = DatabaseClient(config.database_url)
        self.database_repository = DatabaseReferenceRepository(self.database_client)
        self.sync_repository = DatabaseSyncRepository(self.database_client)
        self.generation_repository = DatabaseGenerationRepository(self.database_client)
        self.taxonomy_classifier = TaxonomyClassifier(load_taxonomy(paths.taxonomy_path))
        self.analysis_service = AnalysisService(self.taxonomy_classifier)
        self.embedding_service = EmbeddingService(
            api_key=self.config.openai_api_key,
            model=self.config.embedding_model,
        )
        self.openai_text_service = OpenAITextService(api_key=self.config.openai_api_key)
        self.youtube_service = (
            YouTubeDataService(config.api_key) if config.api_key else None
        )
        transcriptlol_service = TranscriptLolService(
            api_key=config.transcriptlol_api_key,
            workspace_id=config.transcriptlol_workspace_id,
            language=config.transcriptlol_language,
            poll_seconds=config.transcriptlol_poll_seconds,
            timeout_seconds=config.transcriptlol_timeout_seconds,
        )
        self.transcript_service = TranscriptService(
            paths.transcripts_dir,
            paths.audio_cache_dir,
            transcriptlol_service=transcriptlol_service,
        )
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
            self.embedding_service
        )

    def retrieve_references(self, request: RetrievalRequest) -> list:
        resolved_platform, resolved_format_label, resolved_hook_label = self._resolve_request_filters(
            query_text=request.query_text,
            platform=request.platform,
            format_label=request.format_label,
            hook_label=request.hook_label,
        )
        references = self._load_reference_library(request.database_id)
        retrieval_service = self._build_retrieval_service()
        return retrieval_service.retrieve(
            references=references,
            query_text=request.query_text,
            platform=resolved_platform,
            format_label=resolved_format_label,
            hook_label=resolved_hook_label,
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
        resolved_platform, resolved_format_label, resolved_hook_label = self._resolve_request_filters(
            query_text=retrieval_request.query_text,
            platform=request.platform,
            format_label=request.format_label,
            hook_label=request.hook_label,
        )
        retrieval_results = self.retrieve_references(retrieval_request)

        generator = ScriptGenerationService(
            api_key=self.config.openai_api_key,
            model=self.config.generation_model,
        )
        payload = generator.generate_script(
            brief=request.to_prompt_brief(),
            retrieval_results=retrieval_results,
            platform=resolved_platform,
            format_label=resolved_format_label,
            hook_label=resolved_hook_label,
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

    def get_topic_suggestions(self, limit: int = 3) -> dict:
        self._require_database()
        if not self.openai_text_service.is_available():
            raise RuntimeError("OpenAI ist nicht verfügbar.")
        recent_100 = self.database_repository.load_recent_videos(100)
        recent_20 = recent_100[:20]
        if not recent_100:
            return {"suggestions": []}

        last_100_counts = Counter()
        last_20_counts = Counter()

        for video in recent_100:
            combo = self._infer_video_type_combo(video)
            if combo:
                last_100_counts[combo] += 1

        for video in recent_20:
            combo = self._infer_video_type_combo(video)
            if combo:
                last_20_counts[combo] += 1

        underrepresented = []
        base_total = max(sum(last_100_counts.values()), 1)
        for combo, count_100 in last_100_counts.items():
            expected_20 = (count_100 / base_total) * min(len(recent_20), 20)
            actual_20 = last_20_counts.get(combo, 0)
            gap = expected_20 - actual_20
            if gap > 0:
                underrepresented.append(
                    {
                        "combo": combo,
                        "count_100": count_100,
                        "count_20": actual_20,
                        "expected_20": round(expected_20, 2),
                        "gap": round(gap, 2),
                    }
                )
        underrepresented.sort(key=lambda item: (-item["gap"], -item["count_100"], item["combo"]))

        references = self._load_reference_library()
        suggestions = []
        used_video_ids = set()

        for item in underrepresented:
            platform, format_label = item["combo"].split("__", 1)
            candidate = self._find_topic_candidate(
                references=references,
                platform=platform,
                format_label=format_label,
                used_video_ids=used_video_ids,
            )
            if not candidate:
                continue
            payload = self.openai_text_service.extract_topic_suggestion(
                title=candidate.get("title", ""),
                transcript_text=candidate.get("transcript_text", ""),
                views=int(candidate.get("views") or 0),
                last_used_at=(candidate.get("last_reused_at") or ""),
            )
            suggestions.append(
                {
                    "topic": str(payload.get("topic", "")).strip()[:90],
                    "reason": (
                        f"{format_label} auf {platform} kam in den letzten 100 Uploads "
                        f"{item['count_100']}x vor, in den letzten 20 aber nur {item['count_20']}x. "
                        f"Die Vorlage machte {int(candidate.get('views') or 0):,} Views."
                    ).replace(",", "."),
                    "last_used_at": self._to_optional_str(candidate.get("last_reused_at")),
                    "views": int(candidate.get("views") or 0),
                    "source_title": candidate.get("title", ""),
                    "source_url": candidate.get("url", ""),
                    "source_id": candidate.get("video_id"),
                    "transcript": candidate.get("transcript_text", "") or "",
                    "script": None,
                }
            )
            used_video_ids.add(candidate.get("video_id"))
            if len(suggestions) >= limit:
                break

        return {"suggestions": suggestions}

    def polish_text(self, text: str) -> dict:
        if not text or not text.strip():
            raise ValueError("text is required")
        if not self.openai_text_service.is_available():
            raise RuntimeError("OpenAI ist nicht verfügbar.")
        return {"polished_text": self.openai_text_service.polish_text(text.strip())}

    def extract_hooks(self, text: str, top_k: int = 6) -> dict:
        if not text or not text.strip():
            raise ValueError("text is required")
        references = self._load_reference_library()
        filtered_references = [
            reference for reference in references
            if int(reference.get("views") or 0) >= 20000
        ]
        retrieval_service = self._build_retrieval_service()
        retrieval_results = retrieval_service.retrieve(
            references=filtered_references,
            query_text=text.strip(),
            top_k=top_k,
            embedding_index=self._load_embedding_index(),
        )
        hooks = []
        for item in retrieval_results:
            reference = item["reference"]
            hook_text = (reference.get("hook_text") or "").strip()
            if not hook_text:
                transcript_text = (reference.get("transcript_text") or "").strip()
                if transcript_text and self.openai_text_service.is_available():
                    hook_text = self.openai_text_service.distill_hook(transcript_text)
                elif transcript_text:
                    hook_text = self._extract_transcript_hook(transcript_text)
            hooks.append(
                {
                    "hook": hook_text,
                    "source_title": reference.get("title", ""),
                    "source_url": reference.get("url", ""),
                    "views": int(reference.get("views") or 0),
                    "score": item["score"],
                }
            )
        return {"hooks": hooks}

    def complete_video(
        self,
        video_url: str,
        final_text: str,
        topic: Optional[str] = None,
        hook: Optional[str] = None,
    ) -> dict:
        if not video_url or not video_url.strip():
            raise ValueError("video_url is required")
        if not final_text or not final_text.strip():
            raise ValueError("final_text is required")
        if not self.youtube_service:
            raise RuntimeError("YouTube API ist nicht verfügbar.")
        if not self.embedding_service.is_available():
            raise RuntimeError("OpenAI ist nicht verfügbar.")

        video_id = self._extract_video_id_from_url(video_url)
        if not video_id:
            raise ValueError("Ungültige YouTube-URL.")

        video = self.youtube_service.fetch_single_video_detail(video_id)
        transcript_text, transcript_source, transcript_status = self._fetch_complete_video_transcript(
            video=video,
            fallback_text=final_text,
        )
        hook_text = (hook or "").strip() or extract_hook_text(topic or video["title"], final_text.strip())
        analyzed = self.analysis_service.analyze_short(
            {
                "video_id": video["video_id"],
                "title": topic or video["title"],
                "views": video["views"],
                "likes": video["likes"],
                "comments": video["comments"],
                "duration_seconds": video["duration_seconds"],
                "published_at": video["published_at"],
                "url": video["url"],
                "transcript_source": transcript_source,
                "transcript_status": transcript_status,
                "transcript_text": transcript_text,
            }
        )
        if analyzed:
            analyzed["hook_text"] = hook_text
            analyzed["title"] = topic or video["title"]

        video_row = {
            "video_id": video["video_id"],
            "title": topic or video["title"],
            "url": video["url"],
            "description": video.get("description", ""),
            "channel": video.get("channel", ""),
            "published_at": video.get("published_at"),
            "duration_seconds": video.get("duration_seconds", 0),
            "views": video.get("views", 0),
            "likes": video.get("likes", 0),
            "comments": video.get("comments", 0),
            "is_short": bool(video.get("is_short")),
            "last_reused_at": "now",
        }

        self._upsert_completed_video(video_row)
        self.sync_repository.upsert_transcripts(
            [
                {
                    "video_id": video["video_id"],
                    "transcript_source": transcript_source,
                    "transcript_status": transcript_status,
                    "transcript_language_code": "",
                    "transcript_language": "",
                    "transcript_is_generated": False,
                    "transcript_text": transcript_text,
                }
            ]
        )
        if analyzed:
            self.sync_repository.upsert_analysis([analyzed])
        embedding_text = self.embedding_service.build_embedding_text(
            {
                "title": topic or video["title"],
                "hook_text": hook_text,
                "platform_labels": analyzed.get("primary_platform_labels", []) if analyzed else [],
                "format_labels": analyzed.get("format_labels", []) if analyzed else [],
                "hook_labels": analyzed.get("hook_labels", []) if analyzed else [],
                "transcript_text": transcript_text,
            }
        )
        vector = self.embedding_service.embed_texts([embedding_text])[0]
        self.sync_repository.upsert_embeddings(
            self.embedding_service.model,
            [{"video_id": video["video_id"], "embedding": vector}],
        )
        self.database_repository.add_references_to_database("default", [video["video_id"]])
        related_refs = self.retrieve_references(RetrievalRequest(query_text=final_text, top_k=5))
        self.database_repository.update_last_reused_at(
            [item["reference"]["video_id"] for item in related_refs] + [video["video_id"]]
        )
        return {"ok": True, "id": video["video_id"]}

    def _resolve_request_filters(
        self,
        query_text: str,
        platform: Optional[str] = None,
        format_label: Optional[str] = None,
        hook_label: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if platform and format_label and hook_label:
            return platform, format_label, hook_label

        inferred = self.taxonomy_classifier.classify_video(
            title=query_text or "",
            transcript_text=query_text or "",
            hook_text=query_text or "",
        )
        resolved_platform = platform or self._first_non_fallback(
            inferred.get("platform_labels", []),
            "other_platform",
        )
        resolved_format_label = format_label or self._first_non_fallback(
            inferred.get("format_labels", []),
            "other_format",
        )
        resolved_hook_label = hook_label or self._first_non_fallback(
            inferred.get("hook_labels", []),
            "other_hook",
        )
        return resolved_platform, resolved_format_label, resolved_hook_label

    @staticmethod
    def _first_non_fallback(labels: list[str], fallback_label: str) -> Optional[str]:
        for label in labels or []:
            if label != fallback_label:
                return label
        return None

    @staticmethod
    def _extract_transcript_hook(transcript_text: str) -> str:
        sentences = split_sentences(transcript_text or "")
        return " ".join(sentences[:2]).strip()[:140]

    def _fetch_complete_video_transcript(self, video: dict, fallback_text: str) -> tuple[str, str, str]:
        try:
            transcript_data = self.transcript_service.fetch_transcript_from_youtube(
                video["video_id"],
                self.config.transcript_languages,
            )
            return transcript_data.get("text", "").strip() or fallback_text.strip(), transcript_data.get("source", "youtube_transcript_api"), "fetched"
        except TranscriptPipelineError:
            return fallback_text.strip(), "manual_final_text", "fallback_final_text"

    def _upsert_completed_video(self, video_row: dict) -> None:
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into videos (
                        video_id, title, url, description, channel, published_at, duration_seconds,
                        views, likes, comments, is_short, last_reused_at, updated_at
                    ) values (
                        %(video_id)s, %(title)s, %(url)s, %(description)s, %(channel)s, %(published_at)s,
                        %(duration_seconds)s, %(views)s, %(likes)s, %(comments)s, %(is_short)s, now(), now()
                    )
                    on conflict (video_id) do update set
                        title = excluded.title,
                        url = excluded.url,
                        description = excluded.description,
                        channel = excluded.channel,
                        published_at = excluded.published_at,
                        duration_seconds = excluded.duration_seconds,
                        views = excluded.views,
                        likes = excluded.likes,
                        comments = excluded.comments,
                        is_short = excluded.is_short,
                        last_reused_at = now(),
                        updated_at = now()
                    """,
                    video_row,
                )
            connection.commit()

    @staticmethod
    def _extract_video_id_from_url(video_url: str) -> Optional[str]:
        parsed = urlparse(video_url.strip())
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").strip("/")
        if "youtube.com" in host and path.startswith("shorts/"):
            return path.split("/", 1)[1].split("/")[0]
        if "youtube.com" in host:
            return parse_qs(parsed.query).get("v", [None])[0]
        if "youtu.be" in host:
            return path.split("/")[0] if path else None
        return None

    @staticmethod
    def _to_optional_str(value) -> Optional[str]:
        if value in (None, ""):
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _infer_video_type_combo(self, video: dict) -> Optional[str]:
        title = video.get("title", "") or ""
        transcript_text = " ".join(
            part for part in [title, video.get("description", "") or ""] if part
        )
        inferred = self.taxonomy_classifier.classify_video(
            title=title,
            transcript_text=transcript_text,
            hook_text=title,
        )
        platform = self._first_non_fallback(inferred.get("platform_labels", []), "other_platform")
        format_label = self._first_non_fallback(inferred.get("format_labels", []), "other_format")
        if not platform or not format_label:
            return None
        return f"{platform}__{format_label}"

    @staticmethod
    def _find_topic_candidate(
        references: list[dict],
        platform: str,
        format_label: str,
        used_video_ids: set[str],
        min_views: int = 50000,
    ) -> Optional[dict]:
        now = datetime.now(timezone.utc)
        published_cutoff = now - timedelta(days=90)
        reused_cutoff = now - timedelta(days=60)
        candidates = [
            reference for reference in references
            if (
                reference.get("video_id") not in used_video_ids
                and int(reference.get("views") or 0) >= min_views
                and platform in reference.get("platform_labels", [])
                and format_label in reference.get("format_labels", [])
                and ApiService._is_reference_old_enough(reference.get("published_at"), published_cutoff)
                and ApiService._is_reference_reusable(reference.get("last_reused_at"), reused_cutoff)
            )
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                int(item.get("views") or 0),
                item.get("published_at") or "",
            ),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _is_reference_old_enough(published_at: Optional[str], cutoff: datetime) -> bool:
        parsed = ApiService._parse_iso_datetime(published_at)
        return bool(parsed and parsed <= cutoff)

    @staticmethod
    def _is_reference_reusable(last_reused_at: Optional[str], cutoff: datetime) -> bool:
        if not last_reused_at:
            return True
        parsed = ApiService._parse_iso_datetime(last_reused_at)
        return bool(parsed and parsed <= cutoff)

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
