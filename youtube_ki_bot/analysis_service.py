import re
from collections import Counter
from math import ceil
from typing import Optional

from youtube_ki_bot.taxonomy_service import TaxonomyClassifier
from youtube_ki_bot.text_utils import (
    HOOK_TRIGGER_WORDS,
    extract_hook_text,
    extract_top_bigrams,
    extract_top_terms,
    normalize_for_matching,
    split_sentences,
    tokenize_words,
)


class AnalysisService:
    def __init__(self, classifier: TaxonomyClassifier):
        self.classifier = classifier

    def analyze_short(self, short: dict) -> Optional[dict]:
        transcript_text = short.get("transcript_text", "").strip()
        if not transcript_text:
            return None
        hook_text = extract_hook_text(short["title"], transcript_text)
        classification = self.classifier.classify_video(short["title"], transcript_text, hook_text)
        style_features = self.compute_style_features(short["title"], transcript_text, hook_text)
        return {
            "video_id": short["video_id"],
            "title": short["title"],
            "views": short["views"],
            "likes": short["likes"],
            "comments": short["comments"],
            "duration_seconds": short["duration_seconds"],
            "published_at": short["published_at"],
            "url": short["url"],
            "transcript_source": short["transcript_source"],
            "transcript_status": short["transcript_status"],
            "hook_text": hook_text,
            "primary_platform_labels": classification["platform_labels"],
            "mentioned_platform_labels": classification["mentioned_platform_labels"],
            "secondary_platform_labels": classification["secondary_platform_labels"],
            "format_labels": classification["format_labels"],
            "hook_labels": classification["hook_labels"],
            "platform_labels_text": ", ".join(classification["platform_labels"]),
            "mentioned_platform_labels_text": ", ".join(classification["mentioned_platform_labels"]),
            "secondary_platform_labels_text": ", ".join(classification["secondary_platform_labels"]),
            "format_labels_text": ", ".join(classification["format_labels"]),
            "hook_labels_text": ", ".join(classification["hook_labels"]),
            "taxonomy_confidence_score": classification["confidence_score"],
            **style_features,
            "transcript_text": transcript_text,
        }

    @staticmethod
    def normalize_existing_analysis_row(short: dict) -> dict:
        normalized = dict(short)
        if "primary_platform_labels" not in normalized:
            normalized["primary_platform_labels"] = list(normalized.get("platform_labels", []))
        if "mentioned_platform_labels" not in normalized:
            normalized["mentioned_platform_labels"] = list(normalized.get("mentioned_platform_labels", []))
        if "secondary_platform_labels" not in normalized:
            normalized["secondary_platform_labels"] = list(normalized.get("secondary_platform_labels", []))
        normalized["platform_labels_text"] = ", ".join(normalized.get("primary_platform_labels", []))
        normalized["mentioned_platform_labels_text"] = ", ".join(
            normalized.get("mentioned_platform_labels", [])
        )
        normalized["secondary_platform_labels_text"] = ", ".join(
            normalized.get("secondary_platform_labels", [])
        )
        normalized["format_labels_text"] = ", ".join(normalized.get("format_labels", []))
        normalized["hook_labels_text"] = ", ".join(normalized.get("hook_labels", []))
        normalized.setdefault("transcript_source", "")
        normalized.setdefault("transcript_status", "")
        normalized.setdefault("transcript_text", "")
        return normalized

    @staticmethod
    def compute_style_features(title: str, transcript_text: str, hook_text: str) -> dict:
        combined_text = f"{title} {transcript_text}".strip()
        normalized_text = normalize_for_matching(combined_text)
        words = tokenize_words(combined_text)
        cta_markers = [
            "folgen", "schau", "hol dir", "bei uns", "bestellt", "bestellung",
            "erklaervideo", "erklarvideo", "erklärvideo", "danke", "viel spass",
        ]
        direct_address_markers = {"du", "dein", "deine", "dir", "dich"}
        return {
            "word_count": len(words),
            "sentence_count": len(split_sentences(transcript_text)),
            "hook_word_count": len(tokenize_words(hook_text)),
            "question_count": combined_text.count("?"),
            "exclamation_count": combined_text.count("!"),
            "number_count": len(re.findall(r"\d+", combined_text)),
            "cta_present": any(marker in normalized_text for marker in cta_markers),
            "direct_address_present": any(word in direct_address_markers for word in words),
            "has_price_or_storage": bool(
                re.search(r"\b(?:tb|gb|euro|128|256|512|2tb)\b", combined_text.lower())
            ),
            "hook_trigger_present": any(
                trigger in normalize_for_matching(hook_text) for trigger in HOOK_TRIGGER_WORDS
            ),
        }

    @staticmethod
    def select_top_reference_rows(analyzed_shorts: list, top_percent: float) -> tuple[list, dict]:
        grouped_rows = []
        memberships_by_video = {}
        groups = []
        for short in analyzed_shorts:
            for label in short["primary_platform_labels"]:
                groups.append(("platform", label, short))
            for label in short["format_labels"]:
                groups.append(("format", label, short))
            for label in short["hook_labels"]:
                groups.append(("hook", label, short))
            for platform_label in short["primary_platform_labels"]:
                for format_label in short["format_labels"]:
                    groups.append(("platform_format", f"{platform_label}__{format_label}", short))

        grouped = {}
        for group_type, label, short in groups:
            grouped.setdefault((group_type, label), []).append(short)

        for (group_type, label), items in grouped.items():
            sorted_items = sorted(items, key=lambda item: item["views"], reverse=True)
            keep_count = max(1, ceil(len(sorted_items) * top_percent))
            for rank, item in enumerate(sorted_items[:keep_count], start=1):
                grouped_rows.append(
                    {
                        "group_type": group_type,
                        "group_label": label,
                        "group_video_count": len(sorted_items),
                        "selected_rank": rank,
                        "selected_count": keep_count,
                        "selection_percent": top_percent,
                        "video_id": item["video_id"],
                        "title": item["title"],
                        "views": item["views"],
                        "likes": item["likes"],
                        "comments": item["comments"],
                        "duration_seconds": item["duration_seconds"],
                        "hook_text": item["hook_text"],
                        "platform_labels": ", ".join(item["primary_platform_labels"]),
                        "mentioned_platform_labels": ", ".join(item["mentioned_platform_labels"]),
                        "format_labels": ", ".join(item["format_labels"]),
                        "hook_labels": ", ".join(item["hook_labels"]),
                        "taxonomy_confidence_score": item["taxonomy_confidence_score"],
                        "url": item["url"],
                    }
                )
                memberships_by_video.setdefault(item["video_id"], []).append(f"{group_type}:{label}")
        grouped_rows.sort(key=lambda row: (row["group_type"], row["group_label"], row["selected_rank"]))
        return grouped_rows, memberships_by_video

    def analyze_shorts(self, enriched_shorts: list, top_percent: float) -> tuple[list, dict, list]:
        analyzed_shorts = []
        all_transcript_texts = []
        platform_counter = Counter()
        format_counter = Counter()
        hook_counter = Counter()

        for short in enriched_shorts:
            analyzed_short = self.analyze_short(short)
            if not analyzed_short:
                continue
            for label in analyzed_short["primary_platform_labels"]:
                platform_counter[label] += 1
            for label in analyzed_short["format_labels"]:
                format_counter[label] += 1
            for label in analyzed_short["hook_labels"]:
                hook_counter[label] += 1
            analyzed_shorts.append(analyzed_short)
            all_transcript_texts.append(analyzed_short["transcript_text"])

        analyzed_shorts.sort(key=lambda short: short["views"], reverse=True)
        top_reference_rows, memberships_by_video = self.select_top_reference_rows(analyzed_shorts, top_percent)
        for short in analyzed_shorts:
            memberships = memberships_by_video.get(short["video_id"], [])
            short["top_reference_group_count"] = len(memberships)
            short["top_reference_groups"] = ", ".join(memberships)
            short["is_top_reference"] = bool(memberships)

        summary = {
            "analyzed_short_count": len(analyzed_shorts),
            "selection_percent": top_percent,
            "top_platforms": [{"label": label, "count": count} for label, count in platform_counter.most_common()],
            "top_formats": [{"label": label, "count": count} for label, count in format_counter.most_common()],
            "top_hooks": [{"label": label, "count": count} for label, count in hook_counter.most_common()],
            "top_terms": extract_top_terms(all_transcript_texts),
            "top_bigrams": extract_top_bigrams(all_transcript_texts),
            "top_hooks_by_views": [
                {
                    "video_id": short["video_id"],
                    "title": short["title"],
                    "views": short["views"],
                    "hook_text": short["hook_text"],
                    "platform_labels": short["primary_platform_labels"],
                    "mentioned_platform_labels": short["mentioned_platform_labels"],
                    "format_labels": short["format_labels"],
                    "hook_labels": short["hook_labels"],
                }
                for short in analyzed_shorts[:10]
            ],
            "top_reference_groups_preview": top_reference_rows[:25],
            "style_summary": {
                "avg_word_count": round(sum(short["word_count"] for short in analyzed_shorts) / len(analyzed_shorts), 2) if analyzed_shorts else 0,
                "avg_hook_word_count": round(sum(short["hook_word_count"] for short in analyzed_shorts) / len(analyzed_shorts), 2) if analyzed_shorts else 0,
                "question_hook_share": round(sum(1 for short in analyzed_shorts if short["question_count"] > 0) / len(analyzed_shorts), 4) if analyzed_shorts else 0,
                "cta_share": round(sum(1 for short in analyzed_shorts if short["cta_present"]) / len(analyzed_shorts), 4) if analyzed_shorts else 0,
                "direct_address_share": round(sum(1 for short in analyzed_shorts if short["direct_address_present"]) / len(analyzed_shorts), 4) if analyzed_shorts else 0,
            },
        }
        return analyzed_shorts, summary, top_reference_rows
