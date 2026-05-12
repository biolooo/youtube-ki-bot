from youtube_ki_bot.analysis_service import AnalysisService
from youtube_ki_bot.settings import load_taxonomy
from youtube_ki_bot.storage import CsvJsonStorage
from youtube_ki_bot.taxonomy_service import TaxonomyClassifier
from youtube_ki_bot.transcript_service import TranscriptService
from youtube_ki_bot.transcriptlol_service import TranscriptLolService
from youtube_ki_bot.youtube_service import YouTubeDataService


class PipelineOrchestrator:
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
        self.storage = CsvJsonStorage()

    @staticmethod
    def print_transcript_summary(enriched_shorts: list) -> None:
        if not enriched_shorts:
            print("Keine Transcript-Daten erzeugt.")
            return
        summary = {"cached": 0, "fetched": 0, "transcribed": 0, "failed": 0}
        for short in enriched_shorts:
            status = short.get("transcript_status", "")
            if status.startswith("failed"):
                summary["failed"] += 1
            elif status == "fetched_transcript_lol":
                summary["fetched"] += 1
            elif status in summary:
                summary[status] += 1
        print("\nTranscript-Zusammenfassung:")
        print(f"Aus Cache geladen: {summary['cached']}")
        print(f"Per youtube-transcript-api geholt: {summary['fetched']}")
        print(f"Per Whisper transkribiert: {summary['transcribed']}")
        print(f"Fehlgeschlagen: {summary['failed']}")

    def print_transcript_method_summary(self) -> None:
        stats = getattr(self.transcript_service, "last_run_stats", {}) or {}
        if not stats:
            return
        print("\nTranscript-Methoden im aktuellen Lauf:")
        print(f"- Cache: {stats.get('cached', 0)}")
        print(f"- youtube-transcript-api: {stats.get('youtube_transcript_api', 0)}")
        print(f"- transcript.lol: {stats.get('transcript_lol', 0)}")
        print(f"- Whisper: {stats.get('whisper', 0)}")
        print(f"- Fehlgeschlagen: {stats.get('failed', 0)}")

    @staticmethod
    def print_analysis_summary(summary: dict) -> None:
        print("\nAnalyse-Zusammenfassung:")
        print(f"Analysierte Shorts: {summary['analyzed_short_count']}")
        print(f"Top-Selektion pro Gruppe: {int(summary['selection_percent'] * 100)}%")
        top_platforms = summary.get("top_platforms", [])[:5]
        if top_platforms:
            print("Top Plattformen:")
            for item in top_platforms:
                print(f"- {item['label']}: {item['count']}")
        top_formats = summary.get("top_formats", [])[:5]
        if top_formats:
            print("Top Formate:")
            for item in top_formats:
                print(f"- {item['label']}: {item['count']}")
        top_terms = summary.get("top_terms", [])[:8]
        if top_terms:
            print("Top Begriffe:")
            for term in top_terms:
                print(f"- {term['term']}: {term['count']}")

    def run(self) -> None:
        uploads_playlist_id = self.youtube_service.get_uploads_playlist_id(self.config.channel_id)
        all_video_ids = self.youtube_service.get_all_video_ids(uploads_playlist_id)
        print(f"\nGefundene Videos insgesamt: {len(all_video_ids)}")

        all_videos = self.youtube_service.fetch_video_details(all_video_ids)
        shorts = self.youtube_service.filter_and_sort_shorts(all_videos)
        print(f"Verarbeitete Videos insgesamt: {len(all_videos)}")
        print(f"Erkannte Shorts (<= 60 Sekunden): {len(shorts)}")

        self.storage.save_shorts_to_csv(shorts, self.paths.output_csv_path)

        enriched_shorts = self.transcript_service.enrich_shorts_with_transcripts(
            shorts=shorts,
            languages=self.config.transcript_languages,
            whisper_model_name=self.config.whisper_model_name,
            keep_audio_files=self.config.keep_audio_files,
            transcript_limit=self.config.transcript_limit,
            transcript_top_percent=self.config.transcript_top_percent,
            transcriptlol_max_workers=self.config.transcriptlol_max_workers,
        )
        self.storage.save_enriched_shorts_to_csv(enriched_shorts, self.paths.transcripts_csv_path)
        self.print_transcript_summary(enriched_shorts)
        self.print_transcript_method_summary()

        analyzed_shorts, analysis_summary, top_reference_rows = self.analysis_service.analyze_shorts(
            enriched_shorts,
            self.config.top_percent,
        )
        self.storage.save_shorts_analysis_to_csv(analyzed_shorts, self.paths.analysis_csv_path)
        self.storage.save_json(analysis_summary, self.paths.analysis_summary_path)
        self.storage.save_top_reference_rows_to_csv(top_reference_rows, self.paths.top_references_csv_path)
        self.storage.save_json(analysis_summary, self.paths.top_references_summary_path)
        self.print_analysis_summary(analysis_summary)

        print(f"\nCSV gespeichert unter: {self.paths.output_csv_path.resolve()}")
        print(f"Transcript-CSV gespeichert unter: {self.paths.transcripts_csv_path.resolve()}")
        print(f"Transcript-Dateien gespeichert unter: {self.paths.transcripts_dir.resolve()}")
        print(f"Analyse-CSV gespeichert unter: {self.paths.analysis_csv_path.resolve()}")
        print(f"Analyse-Summary gespeichert unter: {self.paths.analysis_summary_path.resolve()}")
        print(f"Top-Referenzen CSV gespeichert unter: {self.paths.top_references_csv_path.resolve()}")
        print(
            f"Top-Referenzen Summary gespeichert unter: "
            f"{self.paths.top_references_summary_path.resolve()}"
        )
