import csv
import json
from pathlib import Path

from youtube_ki_bot.database import DatabaseClient
from youtube_ki_bot.database_reference_repository import DatabaseReferenceRepository


def _read_csv_rows(path: Path) -> list:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _split_labels(raw_value: str) -> list:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _to_bool(raw_value) -> bool:
    return str(raw_value).strip().lower() in {"1", "true", "yes", "ja", "on"}


def _to_int(raw_value, default: int = 0) -> int:
    if raw_value in (None, ""):
        return default
    return int(raw_value)


def _to_float(raw_value, default: float = 0.0) -> float:
    if raw_value in (None, ""):
        return default
    return float(raw_value)


def _embedding_to_vector_literal(values: list) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


class DatabaseImporter:
    def __init__(self, database_client: DatabaseClient, paths):
        self.database_client = database_client
        self.paths = paths

    def import_all(self) -> dict:
        if not self.database_client.is_configured():
            raise ValueError("DATABASE_URL fehlt.")

        video_rows = _read_csv_rows(self.paths.output_csv_path)
        transcript_rows = _read_csv_rows(self.paths.transcripts_csv_path)
        analysis_rows = _read_csv_rows(self.paths.analysis_csv_path)
        reference_rows = _read_csv_rows(self.paths.top_references_csv_path)
        embedding_payload = {}
        if self.paths.embedding_index_path.exists():
            embedding_payload = json.loads(self.paths.embedding_index_path.read_text(encoding="utf-8"))

        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                video_count = self._upsert_videos(cursor, video_rows)
                transcript_count = self._upsert_transcripts(cursor, transcript_rows)
                analysis_count = self._upsert_analysis(cursor, analysis_rows)
                reference_count = self._replace_reference_memberships(cursor, reference_rows)
                embedding_count = self._upsert_embeddings(cursor, embedding_payload)
            connection.commit()

        return {
            "videos": video_count,
            "transcripts": transcript_count,
            "analysis": analysis_count,
            "reference_memberships": reference_count,
            "embeddings": embedding_count,
        }

    def import_from_reference_library(self) -> dict:
        if not self.database_client.is_configured():
            raise ValueError("DATABASE_URL fehlt.")
        if not self.paths.reference_library_path.exists():
            raise FileNotFoundError(
                f"Referenzbibliothek fehlt: {self.paths.reference_library_path}"
            )

        references_payload = json.loads(
            self.paths.reference_library_path.read_text(encoding="utf-8")
        )
        references = references_payload.get("references", [])

        embedding_payload = {}
        if self.paths.embedding_index_path.exists():
            embedding_payload = json.loads(
                self.paths.embedding_index_path.read_text(encoding="utf-8")
            )

        transcript_payload_by_video = {}
        if self.paths.transcripts_dir.exists():
            for transcript_path in self.paths.transcripts_dir.glob("*.json"):
                try:
                    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                video_id = payload.get("video_id")
                if video_id:
                    transcript_payload_by_video[video_id] = payload

        video_rows = self._build_video_rows_from_references(references)
        transcript_rows = self._build_transcript_rows_from_references(
            references,
            transcript_payload_by_video,
        )
        analysis_rows = self._build_analysis_rows_from_references(references)
        reference_rows = self._build_reference_membership_rows(references)

        repository = DatabaseReferenceRepository(self.database_client)
        repository.ensure_multi_database_support()

        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                video_count = self._upsert_videos(cursor, video_rows)
                transcript_count = self._upsert_transcripts(cursor, transcript_rows)
                analysis_count = self._upsert_analysis(cursor, analysis_rows)
                reference_count = self._replace_reference_memberships(cursor, reference_rows)
                embedding_count = self._upsert_embeddings(cursor, embedding_payload)
            connection.commit()

        repository.add_references_to_database(
            "default",
            [reference["video_id"] for reference in references],
        )

        return {
            "videos": video_count,
            "transcripts": transcript_count,
            "analysis": analysis_count,
            "reference_memberships": reference_count,
            "embeddings": embedding_count,
            "database_references": len(references),
        }

    @staticmethod
    def _build_video_rows_from_references(references: list) -> list:
        return [
            {
                "video_id": reference["video_id"],
                "title": reference.get("title", ""),
                "url": reference.get("url", ""),
                "published_at": reference.get("published_at") or None,
                "duration_seconds": int(reference.get("duration_seconds", 0) or 0),
                "views": int(reference.get("views", 0) or 0),
                "likes": int(reference.get("likes", 0) or 0),
                "comments": int(reference.get("comments", 0) or 0),
            }
            for reference in references
        ]

    @staticmethod
    def _build_transcript_rows_from_references(
        references: list,
        transcript_payload_by_video: dict,
    ) -> list:
        rows = []
        for reference in references:
            payload = transcript_payload_by_video.get(reference["video_id"], {})
            rows.append(
                {
                    "video_id": reference["video_id"],
                    "transcript_source": payload.get("transcript_source") or "reference_library",
                    "transcript_status": "backfilled",
                    "transcript_language_code": payload.get("language_code") or "",
                    "transcript_language": payload.get("language") or "",
                    "transcript_is_generated": payload.get("is_generated", False),
                    "transcript_text": payload.get("text") or reference.get("transcript_text", ""),
                    "segments_json": json.dumps(payload.get("segments", []), ensure_ascii=False),
                }
            )
        return rows

    @staticmethod
    def _build_analysis_rows_from_references(references: list) -> list:
        rows = []
        for reference in references:
            top_reference_groups = reference.get("top_reference_groups", [])
            if isinstance(top_reference_groups, list):
                top_reference_groups_text = ", ".join(top_reference_groups)
            else:
                top_reference_groups_text = str(top_reference_groups or "")
            rows.append(
                {
                    "video_id": reference["video_id"],
                    "hook_text": reference.get("hook_text", ""),
                    "platform_labels_text": ", ".join(reference.get("platform_labels", [])),
                    "mentioned_platform_labels_text": ", ".join(
                        reference.get("mentioned_platform_labels", [])
                    ),
                    "secondary_platform_labels_text": ", ".join(
                        reference.get("secondary_platform_labels", [])
                    ),
                    "format_labels_text": ", ".join(reference.get("format_labels", [])),
                    "hook_labels_text": ", ".join(reference.get("hook_labels", [])),
                    "taxonomy_confidence_score": reference.get("taxonomy_confidence_score", 0),
                    "word_count": reference.get("word_count", 0),
                    "question_count": reference.get("question_count", 0),
                    "exclamation_count": reference.get("exclamation_count", 0),
                    "cta_present": reference.get("cta_present", False),
                    "direct_address_present": reference.get("direct_address_present", False),
                    "is_top_reference": reference.get("is_top_reference", False),
                    "top_reference_group_count": reference.get("top_reference_group_count", 0),
                    "top_reference_groups": top_reference_groups_text,
                    "like_rate": reference.get("like_rate", 0),
                    "comment_rate": reference.get("comment_rate", 0),
                    "likes": reference.get("likes", 0),
                    "views": reference.get("views", 0),
                    "comments": reference.get("comments", 0),
                }
            )
        return rows

    @staticmethod
    def _build_reference_membership_rows(references: list) -> list:
        rows = []
        for reference in references:
            for membership in reference.get("reference_memberships", []):
                rows.append(
                    {
                        "video_id": reference["video_id"],
                        "group_type": membership.get("group_type", ""),
                        "group_label": membership.get("group_label", ""),
                        "selected_rank": membership.get("selected_rank", 0),
                        "group_video_count": membership.get("group_video_count", 0),
                        "selection_percent": membership.get("selection_percent", 0),
                    }
                )
        return rows

    @staticmethod
    def _upsert_videos(cursor, rows: list) -> int:
        sql = """
        insert into videos (
            video_id, title, url, published_at, duration_seconds,
            views, likes, comments, is_short, updated_at
        ) values (
            %(video_id)s, %(title)s, %(url)s, %(published_at)s, %(duration_seconds)s,
            %(views)s, %(likes)s, %(comments)s, %(is_short)s, now()
        )
        on conflict (video_id) do update set
            title = excluded.title,
            url = excluded.url,
            published_at = excluded.published_at,
            duration_seconds = excluded.duration_seconds,
            views = excluded.views,
            likes = excluded.likes,
            comments = excluded.comments,
            is_short = excluded.is_short,
            updated_at = now()
        """
        payload = [
            {
                "video_id": row["video_id"],
                "title": row["title"],
                "url": row["url"],
                "published_at": row.get("published_at") or None,
                "duration_seconds": _to_int(row.get("duration_seconds")),
                "views": _to_int(row.get("views")),
                "likes": _to_int(row.get("likes")),
                "comments": _to_int(row.get("comments")),
                "is_short": True,
            }
            for row in rows
        ]
        if payload:
            cursor.executemany(sql, payload)
        return len(payload)

    @staticmethod
    def _upsert_transcripts(cursor, rows: list) -> int:
        sql = """
        insert into transcripts (
            video_id, transcript_source, transcript_status, language_code, language,
            is_generated, transcript_text, segments_json, updated_at
        ) values (
            %(video_id)s, %(transcript_source)s, %(transcript_status)s, %(language_code)s, %(language)s,
            %(is_generated)s, %(transcript_text)s, %(segments_json)s::jsonb, now()
        )
        on conflict (video_id) do update set
            transcript_source = excluded.transcript_source,
            transcript_status = excluded.transcript_status,
            language_code = excluded.language_code,
            language = excluded.language,
            is_generated = excluded.is_generated,
            transcript_text = excluded.transcript_text,
            segments_json = excluded.segments_json,
            updated_at = now()
        """
        payload = []
        for row in rows:
            payload.append(
                {
                    "video_id": row["video_id"],
                    "transcript_source": row.get("transcript_source") or None,
                    "transcript_status": row.get("transcript_status") or None,
                    "language_code": row.get("transcript_language_code") or None,
                    "language": row.get("transcript_language") or None,
                    "is_generated": _to_bool(row.get("transcript_is_generated")),
                    "transcript_text": row.get("transcript_text", ""),
                    "segments_json": row.get("segments_json", "[]"),
                }
            )
        if payload:
            cursor.executemany(sql, payload)
        return len(payload)

    @staticmethod
    def _upsert_analysis(cursor, rows: list) -> int:
        sql = """
        insert into video_analysis (
            video_id, hook_text, platform_labels, mentioned_platform_labels, secondary_platform_labels,
            format_labels, hook_labels, taxonomy_confidence_score, word_count, question_count,
            exclamation_count, cta_present, direct_address_present, is_top_reference,
            top_reference_group_count, top_reference_groups, like_rate, comment_rate, updated_at
        ) values (
            %(video_id)s, %(hook_text)s, %(platform_labels)s, %(mentioned_platform_labels)s, %(secondary_platform_labels)s,
            %(format_labels)s, %(hook_labels)s, %(taxonomy_confidence_score)s, %(word_count)s, %(question_count)s,
            %(exclamation_count)s, %(cta_present)s, %(direct_address_present)s, %(is_top_reference)s,
            %(top_reference_group_count)s, %(top_reference_groups)s, %(like_rate)s, %(comment_rate)s, now()
        )
        on conflict (video_id) do update set
            hook_text = excluded.hook_text,
            platform_labels = excluded.platform_labels,
            mentioned_platform_labels = excluded.mentioned_platform_labels,
            secondary_platform_labels = excluded.secondary_platform_labels,
            format_labels = excluded.format_labels,
            hook_labels = excluded.hook_labels,
            taxonomy_confidence_score = excluded.taxonomy_confidence_score,
            word_count = excluded.word_count,
            question_count = excluded.question_count,
            exclamation_count = excluded.exclamation_count,
            cta_present = excluded.cta_present,
            direct_address_present = excluded.direct_address_present,
            is_top_reference = excluded.is_top_reference,
            top_reference_group_count = excluded.top_reference_group_count,
            top_reference_groups = excluded.top_reference_groups,
            like_rate = excluded.like_rate,
            comment_rate = excluded.comment_rate,
            updated_at = now()
        """
        payload = [
            {
                "video_id": row["video_id"],
                "hook_text": row.get("hook_text") or None,
                "platform_labels": _split_labels(row.get("platform_labels_text", "")),
                "mentioned_platform_labels": _split_labels(row.get("mentioned_platform_labels_text", "")),
                "secondary_platform_labels": _split_labels(row.get("secondary_platform_labels_text", "")),
                "format_labels": _split_labels(row.get("format_labels_text", "")),
                "hook_labels": _split_labels(row.get("hook_labels_text", "")),
                "taxonomy_confidence_score": _to_float(row.get("taxonomy_confidence_score")),
                "word_count": _to_int(row.get("word_count")),
                "question_count": _to_int(row.get("question_count")),
                "exclamation_count": _to_int(row.get("exclamation_count")),
                "cta_present": _to_bool(row.get("cta_present")),
                "direct_address_present": _to_bool(row.get("direct_address_present")),
                "is_top_reference": _to_bool(row.get("is_top_reference")),
                "top_reference_group_count": _to_int(row.get("top_reference_group_count")),
                "top_reference_groups": _split_labels(row.get("top_reference_groups", "")),
                "like_rate": _to_float(row.get("likes")) / _to_int(row.get("views"), 1),
                "comment_rate": _to_float(row.get("comments")) / _to_int(row.get("views"), 1),
            }
            for row in rows
        ]
        if payload:
            cursor.executemany(sql, payload)
        return len(payload)

    @staticmethod
    def _replace_reference_memberships(cursor, rows: list) -> int:
        cursor.execute("delete from reference_memberships")
        sql = """
        insert into reference_memberships (
            video_id, group_type, group_label, selected_rank, group_video_count, selection_percent
        ) values (
            %(video_id)s, %(group_type)s, %(group_label)s, %(selected_rank)s, %(group_video_count)s, %(selection_percent)s
        )
        """
        payload = [
            {
                "video_id": row["video_id"],
                "group_type": row["group_type"],
                "group_label": row["group_label"],
                "selected_rank": _to_int(row.get("selected_rank")),
                "group_video_count": _to_int(row.get("group_video_count")),
                "selection_percent": _to_float(row.get("selection_percent")),
            }
            for row in rows
        ]
        if payload:
            cursor.executemany(sql, payload)
        return len(payload)

    @staticmethod
    def _upsert_embeddings(cursor, embedding_payload: dict) -> int:
        items = embedding_payload.get("items", []) if embedding_payload else []
        model = embedding_payload.get("model", "")
        sql = """
        insert into reference_embeddings (
            video_id, model, embedding, updated_at
        ) values (
            %(video_id)s, %(model)s, %(embedding)s::vector, now()
        )
        on conflict (video_id) do update set
            model = excluded.model,
            embedding = excluded.embedding,
            updated_at = now()
        """
        payload = [
            {
                "video_id": item["video_id"],
                "model": model,
                "embedding": _embedding_to_vector_literal(item["embedding"]),
            }
            for item in items
        ]
        if payload:
            cursor.executemany(sql, payload)
        return len(payload)
