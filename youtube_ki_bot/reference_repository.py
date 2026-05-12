import csv
from pathlib import Path


def _split_csv_labels(raw_value: str) -> list:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


class ReferenceRepository:
    def __init__(self, analysis_csv_path: Path, top_references_csv_path: Path):
        self.analysis_csv_path = analysis_csv_path
        self.top_references_csv_path = top_references_csv_path

    @staticmethod
    def _load_csv_rows(csv_path: Path) -> list:
        if not csv_path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {csv_path}")
        with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
            return list(csv.DictReader(csv_file))

    def load_analysis_rows(self) -> list:
        return self._load_csv_rows(self.analysis_csv_path)

    def load_top_reference_rows(self) -> list:
        return self._load_csv_rows(self.top_references_csv_path)

    def build_reference_library(self) -> list:
        analysis_rows = self.load_analysis_rows()
        top_reference_rows = self.load_top_reference_rows()

        memberships_by_video = {}
        for row in top_reference_rows:
            memberships_by_video.setdefault(row["video_id"], []).append(
                {
                    "group_type": row["group_type"],
                    "group_label": row["group_label"],
                    "selected_rank": int(row["selected_rank"]),
                    "group_video_count": int(row["group_video_count"]),
                    "selection_percent": float(row["selection_percent"]),
                }
            )

        references = []
        for row in analysis_rows:
            views = int(row.get("views", 0) or 0)
            likes = int(row.get("likes", 0) or 0)
            comments = int(row.get("comments", 0) or 0)
            like_rate = round(likes / views, 6) if views else 0
            comment_rate = round(comments / views, 6) if views else 0

            reference = {
                "video_id": row["video_id"],
                "title": row["title"],
                "url": row["url"],
                "views": views,
                "likes": likes,
                "comments": comments,
                "duration_seconds": int(row.get("duration_seconds", 0) or 0),
                "published_at": row.get("published_at", ""),
                "hook_text": row.get("hook_text", ""),
                "platform_labels": _split_csv_labels(row.get("platform_labels_text", "")),
                "mentioned_platform_labels": _split_csv_labels(
                    row.get("mentioned_platform_labels_text", "")
                ),
                "secondary_platform_labels": _split_csv_labels(
                    row.get("secondary_platform_labels_text", "")
                ),
                "format_labels": _split_csv_labels(row.get("format_labels_text", "")),
                "hook_labels": _split_csv_labels(row.get("hook_labels_text", "")),
                "taxonomy_confidence_score": float(
                    row.get("taxonomy_confidence_score", 0) or 0
                ),
                "word_count": int(row.get("word_count", 0) or 0),
                "question_count": int(row.get("question_count", 0) or 0),
                "exclamation_count": int(row.get("exclamation_count", 0) or 0),
                "cta_present": str(row.get("cta_present", "")).lower() == "true",
                "direct_address_present": str(
                    row.get("direct_address_present", "")
                ).lower() == "true",
                "is_top_reference": str(row.get("is_top_reference", "")).lower() == "true",
                "top_reference_group_count": int(
                    row.get("top_reference_group_count", 0) or 0
                ),
                "top_reference_groups": _split_csv_labels(row.get("top_reference_groups", "")),
                "transcript_text": row.get("transcript_text", ""),
                "like_rate": like_rate,
                "comment_rate": comment_rate,
                "reference_memberships": memberships_by_video.get(row["video_id"], []),
            }
            references.append(reference)

        references.sort(key=lambda item: item["views"], reverse=True)
        return references
