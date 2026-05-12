import csv
import json
from pathlib import Path


class CsvJsonStorage:
    @staticmethod
    def save_rows(rows: list, fieldnames: list, output_path: Path) -> None:
        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})

    @staticmethod
    def save_json(payload: dict, output_path: Path) -> None:
        with output_path.open("w", encoding="utf-8") as json_file:
            json.dump(payload, json_file, ensure_ascii=False, indent=2)

    def save_shorts_to_csv(self, shorts: list, output_path: Path) -> None:
        self.save_rows(
            shorts,
            [
                "video_id", "title", "views", "likes", "comments",
                "duration_seconds", "published_at", "url",
            ],
            output_path,
        )

    def save_enriched_shorts_to_csv(self, enriched_shorts: list, output_path: Path) -> None:
        self.save_rows(
            enriched_shorts,
            [
                "video_id", "title", "views", "likes", "comments", "duration_seconds",
                "published_at", "url", "transcript_source", "transcript_language_code",
                "transcript_language", "transcript_is_generated", "transcript_status",
                "transcript_text", "transcript_txt_path", "transcript_json_path",
            ],
            output_path,
        )

    def save_shorts_analysis_to_csv(self, analyzed_shorts: list, output_path: Path) -> None:
        self.save_rows(
            analyzed_shorts,
            [
                "video_id", "title", "views", "likes", "comments", "duration_seconds",
                "published_at", "url", "transcript_source", "transcript_status",
                "hook_text", "platform_labels_text", "mentioned_platform_labels_text",
                "secondary_platform_labels_text", "format_labels_text",
                "hook_labels_text", "taxonomy_confidence_score", "word_count",
                "sentence_count", "hook_word_count", "question_count",
                "exclamation_count", "number_count", "cta_present",
                "direct_address_present", "has_price_or_storage",
                "hook_trigger_present", "is_top_reference",
                "top_reference_group_count", "top_reference_groups", "transcript_text",
            ],
            output_path,
        )

    def save_top_reference_rows_to_csv(self, reference_rows: list, output_path: Path) -> None:
        self.save_rows(
            reference_rows,
            [
                "group_type", "group_label", "group_video_count", "selected_rank",
                "selected_count", "selection_percent", "video_id", "title", "views",
                "likes", "comments", "duration_seconds", "hook_text",
                "platform_labels", "mentioned_platform_labels", "format_labels", "hook_labels",
                "taxonomy_confidence_score", "url",
            ],
            output_path,
        )
