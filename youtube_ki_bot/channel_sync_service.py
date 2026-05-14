from youtube_ki_bot.analysis_service import AnalysisService
from youtube_ki_bot.database import DatabaseClient
from youtube_ki_bot.database_reference_repository import DatabaseReferenceRepository
from youtube_ki_bot.database_sync_repository import DatabaseSyncRepository
from youtube_ki_bot.embedding_service import EmbeddingService
from youtube_ki_bot.settings import load_taxonomy
from youtube_ki_bot.taxonomy_service import TaxonomyClassifier
from youtube_ki_bot.transcript_service import TranscriptService
from youtube_ki_bot.transcriptlol_service import TranscriptLolService
from youtube_ki_bot.youtube_service import YouTubeDataService


class ChannelSyncService:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        taxonomy = load_taxonomy(paths.taxonomy_path)
        self.youtube_service = YouTubeDataService(config.api_key)
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
        self.analysis_service = AnalysisService(TaxonomyClassifier(taxonomy))
        self.database_client = DatabaseClient(config.database_url)
        self.reference_repository = DatabaseReferenceRepository(self.database_client)
        self.sync_repository = DatabaseSyncRepository(self.database_client)
        self.embedding_service = EmbeddingService(
            api_key=config.openai_api_key,
            model=config.embedding_model,
        )

    def run(self) -> dict:
        if not self.sync_repository.is_configured():
            raise ValueError("DATABASE_URL fehlt.")

        existing_video_ids = self.sync_repository.load_existing_video_ids()

        uploads_playlist_id = self.youtube_service.get_uploads_playlist_id(self.config.channel_id)
        all_video_ids = self.youtube_service.get_all_video_ids(uploads_playlist_id)
        all_videos = self.youtube_service.fetch_video_details(all_video_ids)
        shorts = self.youtube_service.filter_and_sort_shorts(all_videos)
        new_shorts = [
            video for video in shorts
            if video["video_id"] not in existing_video_ids
        ]

        updated_videos = self.sync_repository.upsert_videos(all_videos)

        enriched_new_shorts = []
        if new_shorts:
            enriched_new_shorts = self.transcript_service.enrich_shorts_with_transcripts(
                shorts=new_shorts,
                languages=self.config.transcript_languages,
                whisper_model_name=self.config.whisper_model_name,
                keep_audio_files=self.config.keep_audio_files,
                transcript_limit=len(new_shorts),
                transcript_top_percent=1.0,
                transcriptlol_max_workers=self.config.transcriptlol_max_workers,
            )

        transcript_updates = self.sync_repository.upsert_transcripts(enriched_new_shorts)
        new_analyzed_shorts = [
            analyzed for analyzed in (
                self.analysis_service.analyze_short(short) for short in enriched_new_shorts
            )
            if analyzed
        ]

        existing_analyzed_shorts = [
            self.analysis_service.normalize_existing_analysis_row(reference)
            for reference in self.reference_repository.load_references()
        ]
        new_ids = {row["video_id"] for row in new_analyzed_shorts}
        merged_analyzed_shorts = [
            row for row in existing_analyzed_shorts if row["video_id"] not in new_ids
        ] + new_analyzed_shorts
        merged_analyzed_shorts.sort(key=lambda row: row["views"], reverse=True)

        top_reference_rows, memberships_by_video = self.analysis_service.select_top_reference_rows(
            merged_analyzed_shorts,
            self.config.top_percent,
        )
        for short in merged_analyzed_shorts:
            memberships = memberships_by_video.get(short["video_id"], [])
            short["top_reference_group_count"] = len(memberships)
            short["top_reference_groups"] = memberships
            short["is_top_reference"] = bool(memberships)

        analysis_updates = self.sync_repository.upsert_analysis(merged_analyzed_shorts)
        membership_updates = self.sync_repository.replace_reference_memberships(top_reference_rows)
        embedding_updates = self._sync_embeddings(new_analyzed_shorts, merged_analyzed_shorts)

        return {
            "videos_seen": len(all_videos),
            "shorts_seen": len(shorts),
            "new_shorts": len(new_shorts),
            "videos_upserted": updated_videos,
            "transcripts_upserted": transcript_updates,
            "analysis_rows_upserted": analysis_updates,
            "reference_memberships_rebuilt": membership_updates,
            "embeddings_upserted": embedding_updates,
            "transcript_method_stats": self.transcript_service.last_run_stats,
        }

    def _sync_embeddings(self, new_analyzed_shorts: list, merged_analyzed_shorts: list) -> int:
        if not self.embedding_service.is_available() or not merged_analyzed_shorts:
            return 0

        existing_embedding_ids = self.sync_repository.load_existing_embedding_video_ids()
        candidates = [
            short for short in merged_analyzed_shorts
            if short["video_id"] not in existing_embedding_ids
        ]
        if not candidates:
            return 0

        texts = [
            self.embedding_service.build_embedding_text(
                {
                    "title": short["title"],
                    "hook_text": short.get("hook_text", ""),
                    "platform_labels": short.get("primary_platform_labels", []),
                    "format_labels": short.get("format_labels", []),
                    "hook_labels": short.get("hook_labels", []),
                    "transcript_text": short.get("transcript_text", ""),
                }
            )
            for short in candidates
        ]
        vectors = self.embedding_service.embed_texts(texts)
        items = [
            {
                "video_id": short["video_id"],
                "embedding": vector,
            }
            for short, vector in zip(candidates, vectors)
        ]
        return self.sync_repository.upsert_embeddings(self.embedding_service.model, items)
