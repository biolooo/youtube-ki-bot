from collections import defaultdict
from typing import Optional

from youtube_ki_bot.database import DatabaseClient


def _parse_vector_text(raw_value: str) -> list[float]:
    if not raw_value:
        return []
    cleaned = raw_value.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    if not cleaned:
        return []
    return [float(item) for item in cleaned.split(",") if item.strip()]


class DatabaseReferenceRepository:
    def __init__(self, database_client: DatabaseClient):
        self.database_client = database_client

    def is_configured(self) -> bool:
        return self.database_client.is_configured()

    def load_references(self) -> list[dict]:
        memberships_by_video = self._load_memberships()
        sql = """
        select
            v.video_id,
            v.title,
            v.url,
            v.views,
            v.likes,
            v.comments,
            v.duration_seconds,
            coalesce(v.published_at::text, '') as published_at,
            coalesce(a.hook_text, '') as hook_text,
            coalesce(a.platform_labels, '{}'::text[]) as platform_labels,
            coalesce(a.mentioned_platform_labels, '{}'::text[]) as mentioned_platform_labels,
            coalesce(a.secondary_platform_labels, '{}'::text[]) as secondary_platform_labels,
            coalesce(a.format_labels, '{}'::text[]) as format_labels,
            coalesce(a.hook_labels, '{}'::text[]) as hook_labels,
            a.taxonomy_confidence_score,
            a.word_count,
            a.question_count,
            a.exclamation_count,
            a.cta_present,
            a.direct_address_present,
            a.is_top_reference,
            a.top_reference_group_count,
            coalesce(a.top_reference_groups, '{}'::text[]) as top_reference_groups,
            coalesce(t.transcript_text, '') as transcript_text,
            a.like_rate,
            a.comment_rate
        from video_analysis a
        join videos v on v.video_id = a.video_id
        left join transcripts t on t.video_id = a.video_id
        order by v.views desc, v.video_id asc
        """
        with self.database_client.dict_cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()

        references = []
        for row in rows:
            references.append(
                {
                    "video_id": row["video_id"],
                    "title": row["title"],
                    "url": row["url"],
                    "views": int(row["views"] or 0),
                    "likes": int(row["likes"] or 0),
                    "comments": int(row["comments"] or 0),
                    "duration_seconds": int(row["duration_seconds"] or 0),
                    "published_at": row["published_at"] or "",
                    "hook_text": row["hook_text"] or "",
                    "platform_labels": list(row["platform_labels"] or []),
                    "mentioned_platform_labels": list(row["mentioned_platform_labels"] or []),
                    "secondary_platform_labels": list(row["secondary_platform_labels"] or []),
                    "format_labels": list(row["format_labels"] or []),
                    "hook_labels": list(row["hook_labels"] or []),
                    "taxonomy_confidence_score": float(row["taxonomy_confidence_score"] or 0),
                    "word_count": int(row["word_count"] or 0),
                    "question_count": int(row["question_count"] or 0),
                    "exclamation_count": int(row["exclamation_count"] or 0),
                    "cta_present": bool(row["cta_present"]),
                    "direct_address_present": bool(row["direct_address_present"]),
                    "is_top_reference": bool(row["is_top_reference"]),
                    "top_reference_group_count": int(row["top_reference_group_count"] or 0),
                    "top_reference_groups": list(row["top_reference_groups"] or []),
                    "transcript_text": row["transcript_text"] or "",
                    "like_rate": float(row["like_rate"] or 0),
                    "comment_rate": float(row["comment_rate"] or 0),
                    "reference_memberships": memberships_by_video.get(row["video_id"], []),
                }
            )
        return references

    def load_embedding_index(self) -> Optional[dict]:
        sql = """
        select video_id, model, embedding::text as embedding_text
        from reference_embeddings
        order by video_id asc
        """
        with self.database_client.dict_cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()

        if not rows:
            return None

        model = rows[0]["model"] or ""
        return {
            "model": model,
            "items": [
                {
                    "video_id": row["video_id"],
                    "embedding": _parse_vector_text(row["embedding_text"] or ""),
                }
                for row in rows
            ],
        }

    def load_option_values(self) -> dict:
        return {
            "platform_examples": self._load_distinct_array_values("platform_labels"),
            "format_examples": self._load_distinct_array_values("format_labels"),
            "hook_examples": self._load_distinct_array_values("hook_labels"),
        }

    def _load_distinct_array_values(self, column_name: str) -> list[str]:
        sql = f"""
        select distinct unnest(coalesce({column_name}, '{{}}'::text[])) as label
        from video_analysis
        where array_length(coalesce({column_name}, '{{}}'::text[]), 1) is not null
        order by label asc
        """
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
        return [row[0] for row in rows if row and row[0]]

    def _load_memberships(self) -> dict[str, list[dict]]:
        sql = """
        select
            video_id,
            group_type,
            group_label,
            selected_rank,
            group_video_count,
            selection_percent
        from reference_memberships
        order by video_id asc, group_type asc, group_label asc, selected_rank asc
        """
        memberships_by_video = defaultdict(list)
        with self.database_client.dict_cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()

        for row in rows:
            memberships_by_video[row["video_id"]].append(
                {
                    "group_type": row["group_type"],
                    "group_label": row["group_label"],
                    "selected_rank": int(row["selected_rank"] or 0),
                    "group_video_count": int(row["group_video_count"] or 0),
                    "selection_percent": float(row["selection_percent"] or 0),
                }
            )
        return memberships_by_video
