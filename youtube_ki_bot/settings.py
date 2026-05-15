import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


MAX_RESULTS_PER_PAGE = 50
SHORTS_MAX_DURATION_SECONDS = 60
DEFAULT_TRANSCRIPT_LANGUAGES = ["de", "en"]
DEFAULT_WHISPER_MODEL = "base"
DEFAULT_TOP_PERFORMER_PERCENT = 0.2
DEFAULT_TRANSCRIPT_TOP_PERCENT = 0.2
YOUTUBE_HTTP_TIMEOUT_SECONDS = 120
YOUTUBE_API_MAX_RETRIES = 5
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_GENERATION_MODEL = "gpt-5.2"
DEFAULT_TRANSCRIPTLOL_LANGUAGE = "de"
DEFAULT_TRANSCRIPTLOL_POLL_SECONDS = 5
DEFAULT_TRANSCRIPTLOL_TIMEOUT_SECONDS = 600
DEFAULT_TRANSCRIPTLOL_MAX_WORKERS = 4
DEFAULT_SYNC_MAX_SHORTS_PER_RUN = 5


@dataclass(frozen=True)
class PipelinePaths:
    base_dir: Path
    output_csv_path: Path
    transcripts_csv_path: Path
    analysis_csv_path: Path
    analysis_summary_path: Path
    top_references_csv_path: Path
    top_references_summary_path: Path
    reference_library_path: Path
    embedding_index_path: Path
    generated_scripts_dir: Path
    taxonomy_path: Path
    transcripts_dir: Path
    audio_cache_dir: Path


@dataclass(frozen=True)
class AppConfig:
    api_key: Optional[str]
    channel_id: Optional[str]
    transcript_languages: list
    whisper_model_name: str
    keep_audio_files: bool
    transcript_limit: Optional[int]
    transcript_top_percent: float
    top_percent: float
    openai_api_key: Optional[str]
    embedding_model: str
    generation_model: str
    transcriptlol_api_key: Optional[str]
    transcriptlol_workspace_id: Optional[str]
    transcriptlol_language: str
    transcriptlol_poll_seconds: int
    transcriptlol_timeout_seconds: int
    transcriptlol_max_workers: int
    sync_max_shorts_per_run: int
    database_url: Optional[str]
    persist_generated_scripts: bool


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def get_env_int(name: str, default=None):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} muss eine ganze Zahl sein.") from exc


def get_env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja", "on"}


def get_env_float(name: str, default=None):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} muss eine Zahl sein.") from exc


def get_transcript_languages() -> list:
    value = os.getenv("TRANSCRIPT_LANGUAGES", ",".join(DEFAULT_TRANSCRIPT_LANGUAGES))
    languages = [language.strip() for language in value.split(",") if language.strip()]
    return languages or DEFAULT_TRANSCRIPT_LANGUAGES


def build_pipeline_paths(base_dir: Path) -> PipelinePaths:
    return PipelinePaths(
        base_dir=base_dir,
        output_csv_path=base_dir / "top_shorts.csv",
        transcripts_csv_path=base_dir / "shorts_with_transcripts.csv",
        analysis_csv_path=base_dir / "shorts_analysis.csv",
        analysis_summary_path=base_dir / "analysis_summary.json",
        top_references_csv_path=base_dir / "top_video_references.csv",
        top_references_summary_path=base_dir / "top_video_references_summary.json",
        reference_library_path=base_dir / "reference_library.json",
        embedding_index_path=base_dir / "embedding_index.json",
        generated_scripts_dir=base_dir / "generated_scripts",
        taxonomy_path=base_dir / "video_taxonomy.json",
        transcripts_dir=base_dir / "transcripts",
        audio_cache_dir=base_dir / "audio_cache",
    )


def load_app_config(base_dir: Path, require_youtube: bool = True) -> tuple[AppConfig, PipelinePaths]:
    load_dotenv()

    api_key = os.getenv("YOUTUBE_API_KEY")
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    if require_youtube and not api_key:
        raise ValueError("YOUTUBE_API_KEY fehlt in der .env-Datei.")
    if require_youtube and not channel_id:
        raise ValueError("YOUTUBE_CHANNEL_ID fehlt in der .env-Datei.")

    top_percent = get_env_float("TOP_PERFORMER_PERCENT", DEFAULT_TOP_PERFORMER_PERCENT)
    if top_percent is None or top_percent <= 0 or top_percent > 1:
        raise ValueError("TOP_PERFORMER_PERCENT muss zwischen 0 und 1 liegen.")
    transcript_top_percent = get_env_float(
        "TRANSCRIPT_TOP_PERCENT",
        DEFAULT_TRANSCRIPT_TOP_PERCENT,
    )
    if (
        transcript_top_percent is None
        or transcript_top_percent <= 0
        or transcript_top_percent > 1
    ):
        raise ValueError("TRANSCRIPT_TOP_PERCENT muss zwischen 0 und 1 liegen.")
    sync_max_shorts_per_run = get_env_int(
        "SYNC_MAX_SHORTS_PER_RUN",
        DEFAULT_SYNC_MAX_SHORTS_PER_RUN,
    )
    if sync_max_shorts_per_run is None or sync_max_shorts_per_run <= 0:
        raise ValueError("SYNC_MAX_SHORTS_PER_RUN muss eine positive ganze Zahl sein.")

    config = AppConfig(
        api_key=api_key,
        channel_id=channel_id,
        transcript_languages=get_transcript_languages(),
        whisper_model_name=os.getenv("WHISPER_MODEL", DEFAULT_WHISPER_MODEL),
        keep_audio_files=get_env_bool("KEEP_AUDIO_FILES", default=False),
        transcript_limit=get_env_int("TRANSCRIPT_MAX_SHORTS"),
        transcript_top_percent=transcript_top_percent,
        top_percent=top_percent,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        generation_model=os.getenv("OPENAI_GENERATION_MODEL", DEFAULT_GENERATION_MODEL),
        transcriptlol_api_key=os.getenv("TRANSCRIPTLOL_API_KEY"),
        transcriptlol_workspace_id=os.getenv("TRANSCRIPTLOL_WORKSPACE_ID"),
        transcriptlol_language=os.getenv(
            "TRANSCRIPTLOL_LANGUAGE",
            DEFAULT_TRANSCRIPTLOL_LANGUAGE,
        ),
        transcriptlol_poll_seconds=get_env_int(
            "TRANSCRIPTLOL_POLL_SECONDS",
            DEFAULT_TRANSCRIPTLOL_POLL_SECONDS,
        ),
        transcriptlol_timeout_seconds=get_env_int(
            "TRANSCRIPTLOL_TIMEOUT_SECONDS",
            DEFAULT_TRANSCRIPTLOL_TIMEOUT_SECONDS,
        ),
        transcriptlol_max_workers=get_env_int(
            "TRANSCRIPTLOL_MAX_WORKERS",
            DEFAULT_TRANSCRIPTLOL_MAX_WORKERS,
        ),
        sync_max_shorts_per_run=sync_max_shorts_per_run,
        database_url=os.getenv("DATABASE_URL"),
        persist_generated_scripts=get_env_bool("PERSIST_GENERATED_SCRIPTS", default=False),
    )
    return config, build_pipeline_paths(base_dir)


def load_taxonomy(taxonomy_path: Path) -> dict:
    if not taxonomy_path.exists():
        raise FileNotFoundError(f"Taxonomie-Datei nicht gefunden: {taxonomy_path}")
    with taxonomy_path.open("r", encoding="utf-8") as taxonomy_file:
        return json.load(taxonomy_file)
