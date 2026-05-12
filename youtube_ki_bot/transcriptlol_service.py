import time

import requests


class TranscriptLolError(RuntimeError):
    pass


class TranscriptLolService:
    BASE_URL = "https://transcript.lol/api/v1"

    def __init__(
        self,
        api_key=None,
        workspace_id=None,
        language="de",
        poll_seconds=5,
        timeout_seconds=600,
    ):
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.language = language
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return bool(self.api_key and self.workspace_id)

    @staticmethod
    def _compact_text(value) -> str:
        text = str(value).replace("\n", " ").replace("\r", " ")
        return " ".join(text.split())[:220]

    def _headers(self) -> dict:
        if not self.api_key:
            raise TranscriptLolError("TRANSCRIPTLOL_API_KEY fehlt.")
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.BASE_URL}{path}"
        response = requests.request(
            method,
            url,
            headers=self._headers(),
            timeout=60,
            **kwargs,
        )
        if response.status_code >= 400:
            raise TranscriptLolError(
                f"transcript.lol API Fehler {response.status_code}: "
                f"{self._compact_text(response.text[:500])}"
            )
        return response.json()

    def create_recording(self, video: dict) -> dict:
        if not self.workspace_id:
            raise TranscriptLolError("TRANSCRIPTLOL_WORKSPACE_ID fehlt.")
        payload = {
            "title": video["title"],
            "source": "YOUTUBE",
            "sourceUrl": video["url"],
            "language": self.language,
            "externalId": video["video_id"],
        }
        return self._request(
            "POST",
            f"/spaces/{self.workspace_id}/recordings",
            json=payload,
        )

    def get_recording(self, recording_id: str) -> dict:
        return self._request(
            "GET",
            f"/spaces/{self.workspace_id}/recordings/{recording_id}",
        )

    def get_transcript(self, recording_id: str) -> dict:
        return self._request(
            "GET",
            f"/spaces/{self.workspace_id}/recordings/{recording_id}/transcript",
        )

    @staticmethod
    def _extract_recording_id(payload: dict):
        for key in ("id", "recordingId"):
            if payload.get(key):
                return payload[key]
        data = payload.get("data", {})
        for key in ("id", "recordingId"):
            if data.get(key):
                return data[key]
        raise TranscriptLolError(f"Keine recording_id in transcript.lol Antwort gefunden: {payload}")

    @staticmethod
    def _extract_transcript_status(metadata: dict) -> str:
        transcript = metadata.get("transcript", {})
        for key in ("status", "state"):
            if transcript.get(key):
                return str(transcript[key]).upper()
        for key in ("transcriptStatus", "status", "state"):
            if metadata.get(key):
                return str(metadata[key]).upper()
        return "UNKNOWN"

    @staticmethod
    def _is_completed_status(status: str) -> bool:
        normalized = str(status).upper()
        return (
            normalized in {"COMPLETE", "COMPLETED", "DONE", "SUCCESS", "READY"}
            or normalized.endswith("_COMPLETE")
        )

    @staticmethod
    def _is_failed_status(status: str) -> bool:
        normalized = str(status).upper()
        return (
            normalized in {"FAILED", "ERROR", "CANCELLED"}
            or normalized.endswith("_FAILED")
            or normalized.endswith("_ERROR")
        )

    @staticmethod
    def _normalize_transcript_payload(payload: dict) -> dict:
        segments = []
        text_parts = []

        raw_segments = payload.get("segments") or payload.get("paragraphs") or payload.get("utterances") or []
        for index, segment in enumerate(raw_segments):
            text = (
                segment.get("text")
                or segment.get("content")
                or segment.get("paragraph")
                or ""
            ).strip()
            if not text:
                continue
            start = segment.get("start") or segment.get("startTime") or segment.get("startMs")
            end = segment.get("end") or segment.get("endTime") or segment.get("endMs")
            segments.append(
                {
                    "index": index,
                    "start": start,
                    "end": end,
                    "text": text,
                }
            )
            text_parts.append(text)

        if not text_parts:
            fallback_text = payload.get("text") or payload.get("transcript") or ""
            fallback_text = fallback_text.strip()
            if fallback_text:
                text_parts.append(fallback_text)
                segments.append({"index": 0, "start": None, "end": None, "text": fallback_text})

        return {
            "source": "transcript_lol",
            "language_code": payload.get("languageCode") or payload.get("spokenLanguageCode") or "",
            "language": payload.get("language") or payload.get("spokenLanguageCode") or "",
            "is_generated": False,
            "segments": segments,
            "text": " ".join(text_parts).strip(),
        }

    def fetch_transcript(self, video: dict, progress_callback=None) -> dict:
        def report(message: str) -> None:
            if progress_callback:
                progress_callback(self._compact_text(message))

        report("transcript.lol angefragt")
        create_payload = self.create_recording(video)
        recording_id = self._extract_recording_id(create_payload)
        report(f"Recording erstellt: {recording_id}; starte Polling")

        started_at = time.time()
        last_status = None
        while True:
            metadata = self.get_recording(recording_id)
            status = self._extract_transcript_status(metadata)

            if status != last_status:
                report(f"Status {status}; warte auf Fertigstellung")
                last_status = status

            if self._is_completed_status(status):
                report("Verarbeitung fertig; lade Transcript")
                transcript_payload = self.get_transcript(recording_id)
                transcript_data = self._normalize_transcript_payload(transcript_payload)
                if transcript_data["text"]:
                    report("Transcript geladen und normalisiert")
                    return transcript_data
                raise TranscriptLolError("transcript.lol hat kein verwertbares Transcript zurückgegeben.")

            if self._is_failed_status(status):
                raise TranscriptLolError(f"transcript.lol Verarbeitung fehlgeschlagen: {status}")

            if time.time() - started_at > self.timeout_seconds:
                raise TranscriptLolError(
                    f"transcript.lol Timeout nach {self.timeout_seconds} Sekunden."
                )

            time.sleep(self.poll_seconds)
