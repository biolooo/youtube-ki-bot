from youtube_ki_bot.database import DatabaseClient
from youtube_ki_bot.database_importer import (
    _embedding_to_vector_literal,
    _split_labels,
    _to_bool,
    _to_float,
    _to_int,
)


class DatabaseSyncRepository:
    def __init__(self, database_client: DatabaseClient):
        self.database_client = database_client

    def is_configured(self) -> bool:
        return self.database_client.is_configured()

    def load_existing_video_ids(self) -> set[str]:
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select video_id from videos")
                return {row[0] for row in cursor.fetchall()}

    def load_existing_embedding_video_ids(self) -> set[str]:
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select video_id from reference_embeddings")
                return {row[0] for row in cursor.fetchall()}

    def load_analyzed_video_ids(self) -> set[str]:
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select video_id from video_analysis")
                return {row[0] for row in cursor.fetchall()}


    def upsert_videos(self, videos: list[dict]) -> int:
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
                "video_id": video["video_id"],
                "title": video["title"],
                "url": video["url"],
                "published_at": video.get("published_at") or None,
                "duration_seconds": int(video.get("duration_seconds", 0) or 0),
                "views": int(video.get("views", 0) or 0),
                "likes": int(video.get("likes", 0) or 0),
                "comments": int(video.get("comments", 0) or 0),
                "is_short": bool(video.get("is_short")),
            }
            for video in videos
        ]
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                if payload:
                    cursor.executemany(sql, payload)
            connection.commit()
        return len(payload)

    def upsert_transcripts(self, enriched_shorts: list[dict]) -> int:
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
        payload = [
            {
                "video_id": short["video_id"],
                "transcript_source": short.get("transcript_source") or None,
                "transcript_status": short.get("transcript_status") or None,
                "language_code": short.get("transcript_language_code") or None,
                "language": short.get("transcript_language") or None,
                "is_generated": _to_bool(short.get("transcript_is_generated")),
                "transcript_text": short.get("transcript_text", ""),
                "segments_json": "[]",
            }
            for short in enriched_shorts
        ]
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                if payload:
                    cursor.executemany(sql, payload)
            connection.commit()
        return len(payload)

    def upsert_analysis(self, analyzed_shorts: list[dict]) -> int:
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
                "platform_labels": self._platform_labels(row),
                "mentioned_platform_labels": self._mentioned_platform_labels(row),
                "secondary_platform_labels": self._secondary_platform_labels(row),
                "format_labels": self._format_labels(row),
                "hook_labels": self._hook_labels(row),
                "taxonomy_confidence_score": _to_float(row.get("taxonomy_confidence_score")),
                "word_count": _to_int(row.get("word_count")),
                "question_count": _to_int(row.get("question_count")),
                "exclamation_count": _to_int(row.get("exclamation_count")),
                "cta_present": _to_bool(row.get("cta_present")),
                "direct_address_present": _to_bool(row.get("direct_address_present")),
                "is_top_reference": _to_bool(row.get("is_top_reference")),
                "top_reference_group_count": _to_int(row.get("top_reference_group_count")),
                "top_reference_groups": self._top_reference_groups(row),
                "like_rate": _to_float(row.get("like_rate")),
                "comment_rate": _to_float(row.get("comment_rate")),
            }
            for row in analyzed_shorts
        ]
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                if payload:
                    cursor.executemany(sql, payload)
            connection.commit()
        return len(payload)

    def replace_reference_memberships(self, rows: list[dict]) -> int:
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
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from reference_memberships")
                if payload:
                    cursor.executemany(sql, payload)
            connection.commit()
        return len(payload)

    def upsert_embeddings(self, model: str, items: list[dict]) -> int:
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
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                if payload:
                    cursor.executemany(sql, payload)
            connection.commit()
        return len(payload)

    @staticmethod
    def _platform_labels(row: dict) -> list[str]:
        if row.get("primary_platform_labels") is not None:
            return list(row.get("primary_platform_labels") or [])
        return list(row.get("platform_labels") or _split_labels(row.get("platform_labels_text", "")))

    @staticmethod
    def _mentioned_platform_labels(row: dict) -> list[str]:
        return list(
            row.get("mentioned_platform_labels")
            or _split_labels(row.get("mentioned_platform_labels_text", ""))
        )

    @staticmethod
    def _secondary_platform_labels(row: dict) -> list[str]:
        return list(
            row.get("secondary_platform_labels")
            or _split_labels(row.get("secondary_platform_labels_text", ""))
        )

    @staticmethod
    def _format_labels(row: dict) -> list[str]:
        return list(row.get("format_labels") or _split_labels(row.get("format_labels_text", "")))

    @staticmethod
    def _hook_labels(row: dict) -> list[str]:
        return list(row.get("hook_labels") or _split_labels(row.get("hook_labels_text", "")))

    @staticmethod
    def _top_reference_groups(row: dict) -> list[str]:
        raw = row.get("top_reference_groups", [])
        if isinstance(raw, list):
            return raw
        return _split_labels(raw)
