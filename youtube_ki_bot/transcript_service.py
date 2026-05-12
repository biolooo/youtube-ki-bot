import json
import shutil
import subprocess
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from math import ceil
from pathlib import Path
from typing import Optional

from youtube_ki_bot.settings import ensure_directory
from youtube_ki_bot.text_utils import flatten_transcript_segments
from youtube_ki_bot.transcriptlol_service import TranscriptLolError, TranscriptLolService


class TranscriptPipelineError(RuntimeError):
    pass


class _SilentYtDlpLogger:
    def debug(self, _msg):
        return None

    def warning(self, _msg):
        return None

    def error(self, _msg):
        return None


class TranscriptService:
    def __init__(
        self,
        transcripts_dir: Path,
        audio_cache_dir: Path,
        transcriptlol_service: Optional[TranscriptLolService] = None,
    ):
        self.transcripts_dir = transcripts_dir
        self.audio_cache_dir = audio_cache_dir
        self.transcriptlol_service = transcriptlol_service
        self._whisper_models = {}
        self.last_run_stats = {}

    @staticmethod
    def _compact_error_text(error) -> str:
        text = str(error).replace("\n", " ").replace("\r", " ")
        text = " ".join(text.split())
        return text[:220]

    @staticmethod
    def _short_title(title: str, max_length: int = 54) -> str:
        clean = " ".join(title.split())
        if len(clean) <= max_length:
            return clean
        return clean[: max_length - 1] + "…"

    def _print_progress_line(self, index: int, total: int, video: dict, outcome: str, stats: dict) -> None:
        print(
            f"[{index}/{total}] {outcome} | "
            f"cache={stats['cached']} yt={stats['youtube_transcript_api']} "
            f"tlol={stats['transcript_lol']} queued={stats.get('queued_transcript_lol', 0)} "
            f"whisper={stats['whisper']} "
            f"failed={stats['failed']} | {video['video_id']} | "
            f"{self._short_title(video['title'])}"
        )

    def _print_transcriptlol_step(self, video: dict, message: str) -> None:
        print(
            f"[tlol-step] {video['video_id']} | "
            f"{self._short_title(video['title'], max_length=42)} | {message}"
        )

    def _resolve_transcriptlol_future(
        self,
        future,
        position: int,
        short: dict,
        total: int,
        completed_tlol: int,
        total_tlol: int,
        whisper_model_name: str,
        keep_audio_files: bool,
        enriched_shorts: list,
        stats: dict,
    ) -> None:
        try:
            transcript_data = future.result()
            transcript_data["status"] = "fetched_transcript_lol"
            self.save_transcript_files(short, transcript_data)
            stats["transcript_lol"] += 1
            stats["queued_transcript_lol"] -= 1
            outcome = f"transcript.lol {completed_tlol}/{total_tlol}"
            enriched_shorts[position] = self._build_enriched_short(short, transcript_data)
        except Exception as exc:
            self._print_transcriptlol_step(
                short,
                "transcript.lol fehlgeschlagen: "
                f"{self._compact_error_text(exc)}; versuche Whisper-Fallback",
            )
            stats["queued_transcript_lol"] -= 1
            try:
                transcript_data = self.fetch_transcript_with_whisper_only(
                    short,
                    whisper_model_name,
                    keep_audio_files,
                )
                self.save_transcript_files(short, transcript_data)
                stats["whisper"] += 1
                outcome = f"whisper {completed_tlol}/{total_tlol}"
                enriched_shorts[position] = self._build_enriched_short(short, transcript_data)
            except TranscriptPipelineError as whisper_exc:
                transcript_data = {
                    "source": "",
                    "language_code": "",
                    "language": "",
                    "is_generated": False,
                    "segments": [],
                    "text": "",
                    "status": f"failed: {self._compact_error_text(whisper_exc)}",
                }
                stats["failed"] += 1
                outcome = f"failed {completed_tlol}/{total_tlol}"
                enriched_shorts[position] = self._build_enriched_short(short, transcript_data)
        self._print_progress_line(
            index=position + 1,
            total=total,
            video=short,
            outcome=outcome,
            stats=stats,
        )

    def get_transcript_paths(self, video_id: str) -> tuple[Path, Path]:
        return (
            self.transcripts_dir / f"{video_id}.txt",
            self.transcripts_dir / f"{video_id}.json",
        )

    def load_cached_transcript(self, video_id: str):
        _, json_path = self.get_transcript_paths(video_id)
        if not json_path.exists():
            return None
        with json_path.open("r", encoding="utf-8") as json_file:
            return json.load(json_file)

    def save_transcript_files(self, video: dict, transcript_data: dict) -> tuple[Path, Path]:
        ensure_directory(self.transcripts_dir)
        text_path, json_path = self.get_transcript_paths(video["video_id"])
        text_path.write_text(transcript_data["text"], encoding="utf-8")
        payload = {
            "video_id": video["video_id"],
            "title": video["title"],
            "url": video["url"],
            "transcript_source": transcript_data["source"],
            "language_code": transcript_data["language_code"],
            "language": transcript_data["language"],
            "is_generated": transcript_data["is_generated"],
            "text": transcript_data["text"],
            "segments": transcript_data["segments"],
        }
        with json_path.open("w", encoding="utf-8") as json_file:
            json.dump(payload, json_file, ensure_ascii=False, indent=2)
        return text_path, json_path

    def fetch_transcript_from_youtube(self, video_id: str, languages: list) -> dict:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError as exc:
            raise TranscriptPipelineError(
                "Package 'youtube-transcript-api' ist nicht installiert."
            ) from exc
        try:
            transcript = YouTubeTranscriptApi().fetch(video_id, languages=languages)
            segments = transcript.to_raw_data()
        except Exception as exc:
            raise TranscriptPipelineError(
                "Kein Transcript per youtube-transcript-api verfügbar: "
                f"{self._compact_error_text(exc)}"
            ) from exc
        return {
            "source": "youtube_transcript_api",
            "language_code": transcript.language_code,
            "language": transcript.language,
            "is_generated": transcript.is_generated,
            "segments": segments,
            "text": flatten_transcript_segments(segments),
        }

    @staticmethod
    def _run_subprocess(command: list) -> None:
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            error_message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise TranscriptPipelineError(self._compact_error_text(error_message)) from exc

    def download_audio_with_ytdlp(self, video: dict) -> Path:
        ensure_directory(self.audio_cache_dir)
        output_template = str(self.audio_cache_dir / f"{video['video_id']}.%(ext)s")
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            yt_dlp_binary = shutil.which("yt-dlp")
            if not yt_dlp_binary:
                raise TranscriptPipelineError(
                    "Weder das Python-Package 'yt-dlp' noch das CLI 'yt-dlp' ist installiert."
                ) from exc
            self._run_subprocess(
                [
                    yt_dlp_binary,
                    "-f", "bestaudio/best",
                    "--no-playlist", "--no-warnings",
                    "-o", output_template,
                    video["url"],
                ]
            )
        else:
            options = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "overwrites": True,
                "logger": _SilentYtDlpLogger(),
            }
            try:
                with YoutubeDL(options) as downloader:
                    downloader.download([video["url"]])
            except Exception as exc:
                raise TranscriptPipelineError(
                    "yt-dlp Download fehlgeschlagen: "
                    f"{self._compact_error_text(exc)}"
                ) from exc

        matching_files = sorted(
            path for path in self.audio_cache_dir.glob(f"{video['video_id']}.*")
            if path.is_file() and path.suffix not in {".json", ".txt"}
        )
        if not matching_files:
            raise TranscriptPipelineError("yt-dlp hat keine Audiodatei erzeugt.")
        return matching_files[0]

    def convert_audio_for_whisper(self, source_path: Path, video_id: str) -> Path:
        ffmpeg_binary = shutil.which("ffmpeg")
        if not ffmpeg_binary:
            raise TranscriptPipelineError("ffmpeg ist nicht installiert oder nicht im PATH verfügbar.")
        output_path = self.audio_cache_dir / f"{video_id}.wav"
        self._run_subprocess(
            [
                ffmpeg_binary, "-y", "-i", str(source_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(output_path),
            ]
        )
        return output_path

    def _load_whisper_model(self, model_name: str):
        if model_name not in self._whisper_models:
            try:
                import whisper
            except ImportError as exc:
                raise TranscriptPipelineError(
                    "Package 'openai-whisper' ist nicht installiert."
                ) from exc
            print(f"Whisper-Modell wird geladen: {model_name}")
            self._whisper_models[model_name] = whisper.load_model(model_name)
        return self._whisper_models[model_name]

    def transcribe_audio_with_whisper(self, audio_path: Path, model_name: str) -> dict:
        model = self._load_whisper_model(model_name)
        result = model.transcribe(str(audio_path))
        segments = [
            {
                "start": segment.get("start"),
                "end": segment.get("end"),
                "text": segment.get("text", "").strip(),
            }
            for segment in result.get("segments", [])
        ]
        return {
            "source": "whisper",
            "language_code": result.get("language", ""),
            "language": result.get("language", ""),
            "is_generated": False,
            "segments": segments,
            "text": result.get("text", "").strip(),
        }

    @staticmethod
    def cleanup_audio_files(*paths: Path) -> None:
        for path in paths:
            if path and path.exists():
                path.unlink()

    def fetch_transcript_with_fallback(
        self,
        video: dict,
        languages: list,
        whisper_model_name: str,
        keep_audio_files: bool,
    ) -> dict:
        try:
            transcript_data = self.fetch_transcript_from_youtube(video["video_id"], languages)
            transcript_data["status"] = "fetched"
            return transcript_data
        except TranscriptPipelineError as youtube_error:
            pass

        if self.transcriptlol_service and self.transcriptlol_service.is_available():
            try:
                transcript_data = self.transcriptlol_service.fetch_transcript(video)
                transcript_data["status"] = "fetched_transcript_lol"
                return transcript_data
            except TranscriptLolError as transcriptlol_error:
                pass

        audio_download_path = None
        whisper_audio_path = None
        try:
            audio_download_path = self.download_audio_with_ytdlp(video)
            whisper_audio_path = self.convert_audio_for_whisper(audio_download_path, video["video_id"])
            transcript_data = self.transcribe_audio_with_whisper(whisper_audio_path, whisper_model_name)
            transcript_data["status"] = "transcribed"
            return transcript_data
        except TranscriptPipelineError as whisper_error:
            raise TranscriptPipelineError(
                f"Whisper-Fallback fehlgeschlagen: {whisper_error}"
            ) from whisper_error
        finally:
            if not keep_audio_files:
                self.cleanup_audio_files(audio_download_path, whisper_audio_path)

    def fetch_transcript_with_whisper_only(
        self,
        video: dict,
        whisper_model_name: str,
        keep_audio_files: bool,
    ) -> dict:
        audio_download_path = None
        whisper_audio_path = None
        try:
            audio_download_path = self.download_audio_with_ytdlp(video)
            whisper_audio_path = self.convert_audio_for_whisper(
                audio_download_path,
                video["video_id"],
            )
            transcript_data = self.transcribe_audio_with_whisper(
                whisper_audio_path,
                whisper_model_name,
            )
            transcript_data["status"] = "transcribed"
            return transcript_data
        except TranscriptPipelineError as whisper_error:
            raise TranscriptPipelineError(
                f"Whisper-Fallback fehlgeschlagen: {whisper_error}"
            ) from whisper_error
        finally:
            if not keep_audio_files:
                self.cleanup_audio_files(audio_download_path, whisper_audio_path)

    def _build_enriched_short(self, short: dict, transcript_data: dict) -> dict:
        text_path, json_path = self.get_transcript_paths(short["video_id"])
        enriched_short = dict(short)
        enriched_short.update(
            {
                "transcript_source": transcript_data["source"],
                "transcript_language_code": transcript_data["language_code"],
                "transcript_language": transcript_data["language"],
                "transcript_is_generated": transcript_data["is_generated"],
                "transcript_status": transcript_data["status"],
                "transcript_text": transcript_data["text"],
                "transcript_txt_path": str(text_path.resolve()) if text_path.exists() else "",
                "transcript_json_path": str(json_path.resolve()) if json_path.exists() else "",
            }
        )
        return enriched_short

    def enrich_shorts_with_transcripts(
        self,
        shorts: list,
        languages: list,
        whisper_model_name: str,
        keep_audio_files: bool,
        transcript_limit: Optional[int],
        transcript_top_percent: float,
        transcriptlol_max_workers: int,
    ) -> list:
        if transcript_limit is not None:
            target_count = max(transcript_limit, 0)
        else:
            target_count = max(1, ceil(len(shorts) * transcript_top_percent)) if shorts else 0
        shorts_to_process = shorts[:target_count]

        print(
            f"\nTranscript-Pipeline startet für {len(shorts_to_process)} Shorts "
            f"(Top {int(transcript_top_percent * 100)}% nach Views) "
            f"mit Sprach-Priorität {languages}."
        )
        stats = {
            "cached": 0,
            "youtube_transcript_api": 0,
            "transcript_lol": 0,
            "queued_transcript_lol": 0,
            "whisper": 0,
            "failed": 0,
        }
        enriched_shorts = [None] * len(shorts_to_process)
        pending_transcriptlol = []
        completed_tlol = 0
        total_submitted_tlol = 0

        executor = None
        queue_capacity = max(1, transcriptlol_max_workers) * 2
        if self.transcriptlol_service and self.transcriptlol_service.is_available():
            executor = ThreadPoolExecutor(max_workers=max(1, transcriptlol_max_workers))

        for index, short in enumerate(shorts_to_process, start=1):
            cached_transcript = self.load_cached_transcript(short["video_id"])
            if cached_transcript:
                transcript_data = {
                    "source": cached_transcript.get("transcript_source", "cache"),
                    "language_code": cached_transcript.get("language_code", ""),
                    "language": cached_transcript.get("language", ""),
                    "is_generated": cached_transcript.get("is_generated", False),
                    "segments": cached_transcript.get("segments", []),
                    "text": cached_transcript.get("text", ""),
                    "status": "cached",
                }
                stats["cached"] += 1
                outcome = "cache"
                enriched_shorts[index - 1] = self._build_enriched_short(short, transcript_data)
            else:
                try:
                    transcript_data = self.fetch_transcript_from_youtube(
                        short["video_id"],
                        languages,
                    )
                    transcript_data["status"] = "fetched"
                    self.save_transcript_files(short, transcript_data)
                    stats["youtube_transcript_api"] += 1
                    outcome = "youtube"
                    enriched_shorts[index - 1] = self._build_enriched_short(short, transcript_data)
                except TranscriptPipelineError:
                    if executor:
                        future = executor.submit(
                            self.transcriptlol_service.fetch_transcript,
                            short,
                            lambda message, video=short: self._print_transcriptlol_step(video, message),
                        )
                        pending_transcriptlol.append((index - 1, short, future))
                        stats["queued_transcript_lol"] += 1
                        total_submitted_tlol += 1
                        outcome = "queued_tlol"
                    else:
                        try:
                            transcript_data = self.fetch_transcript_with_whisper_only(
                                short,
                                whisper_model_name,
                                keep_audio_files,
                            )
                            self.save_transcript_files(short, transcript_data)
                            stats["whisper"] += 1
                            outcome = "whisper"
                            enriched_shorts[index - 1] = self._build_enriched_short(short, transcript_data)
                        except TranscriptPipelineError as exc:
                            transcript_data = {
                                "source": "",
                                "language_code": "",
                                "language": "",
                                "is_generated": False,
                                "segments": [],
                                "text": "",
                                "status": f"failed: {self._compact_error_text(exc)}",
                            }
                            stats["failed"] += 1
                            outcome = "failed"
                            enriched_shorts[index - 1] = self._build_enriched_short(short, transcript_data)
            self._print_progress_line(
                index=index,
                total=len(shorts_to_process),
                video=short,
                outcome=outcome,
                stats=stats,
            )

            if pending_transcriptlol:
                future_map = {
                    future: (position, pending_short)
                    for position, pending_short, future in pending_transcriptlol
                }
                wait_timeout = 0
                if len(pending_transcriptlol) >= queue_capacity:
                    wait_timeout = None
                done, _ = wait(
                    list(future_map.keys()),
                    timeout=wait_timeout,
                    return_when=FIRST_COMPLETED,
                )
                if done:
                    remaining = []
                    for position, pending_short, future in pending_transcriptlol:
                        if future in done:
                            completed_tlol += 1
                            self._resolve_transcriptlol_future(
                                future=future,
                                position=position,
                                short=pending_short,
                                total=len(shorts_to_process),
                                completed_tlol=completed_tlol,
                                total_tlol=total_submitted_tlol,
                                whisper_model_name=whisper_model_name,
                                keep_audio_files=keep_audio_files,
                                enriched_shorts=enriched_shorts,
                                stats=stats,
                            )
                        else:
                            remaining.append((position, pending_short, future))
                    pending_transcriptlol = remaining

        future_map = {
            future: (position, short)
            for position, short, future in pending_transcriptlol
        }
        for future in as_completed(future_map) if future_map else []:
            position, short = future_map[future]
            completed_tlol += 1
            self._resolve_transcriptlol_future(
                future=future,
                position=position,
                short=short,
                total=len(shorts_to_process),
                completed_tlol=completed_tlol,
                total_tlol=total_submitted_tlol,
                whisper_model_name=whisper_model_name,
                keep_audio_files=keep_audio_files,
                enriched_shorts=enriched_shorts,
                stats=stats,
            )

        if executor:
            executor.shutdown(wait=True)

        self.last_run_stats = stats
        return [item for item in enriched_shorts if item is not None]
