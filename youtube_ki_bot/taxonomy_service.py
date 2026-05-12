from youtube_ki_bot.text_utils import normalize_for_matching


TITLE_WEIGHT = 3
HOOK_WEIGHT = 2
TRANSCRIPT_WEIGHT = 1


class TaxonomyClassifier:
    def __init__(self, taxonomy: dict):
        self.taxonomy = taxonomy

    @staticmethod
    def _count_hits(text: str, keywords: list) -> int:
        if not text:
            return 0
        return sum(1 for keyword in keywords if keyword and keyword in text)

    def _score_group(self, title: str, transcript_text: str, hook_text: str, taxonomy_group: dict) -> dict:
        normalized_title = normalize_for_matching(title)
        normalized_transcript = normalize_for_matching(transcript_text)
        normalized_hook = normalize_for_matching(hook_text)

        scores = {}
        title_hits = {}
        transcript_hits = {}
        hook_hits = {}

        for label, config in taxonomy_group.items():
            keywords = [normalize_for_matching(keyword) for keyword in config.get("keywords", [])]
            current_title_hits = self._count_hits(normalized_title, keywords)
            current_hook_hits = self._count_hits(normalized_hook, keywords)
            current_transcript_hits = self._count_hits(normalized_transcript, keywords)

            weighted_score = (
                current_title_hits * TITLE_WEIGHT
                + current_hook_hits * HOOK_WEIGHT
                + current_transcript_hits * TRANSCRIPT_WEIGHT
            )
            if weighted_score > 0:
                scores[label] = weighted_score
                title_hits[label] = current_title_hits
                transcript_hits[label] = current_transcript_hits
                hook_hits[label] = current_hook_hits

        return {
            "scores": scores,
            "title_hits": title_hits,
            "transcript_hits": transcript_hits,
            "hook_hits": hook_hits,
        }

    @staticmethod
    def _sorted_labels(scores: dict) -> list:
        return [
            label for label, _score in sorted(
                scores.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

    def _classify_platforms(self, title: str, transcript_text: str, hook_text: str) -> dict:
        result = self._score_group(
            title,
            transcript_text,
            hook_text,
            self.taxonomy.get("platforms", {}),
        )
        scores = result["scores"]
        title_hits = result["title_hits"]
        transcript_hits = result["transcript_hits"]
        hook_hits = result["hook_hits"]

        mentioned_labels = self._sorted_labels(scores)
        primary_labels = []
        secondary_labels = []

        for label in mentioned_labels:
            has_title_signal = title_hits.get(label, 0) > 0
            has_hook_signal = hook_hits.get(label, 0) > 0
            transcript_strength = transcript_hits.get(label, 0)
            weighted_score = scores[label]

            if has_title_signal or has_hook_signal or weighted_score >= 3 or transcript_strength >= 2:
                primary_labels.append(label)
            else:
                secondary_labels.append(label)

        if not primary_labels:
            primary_labels = ["other_platform"]
            scores["other_platform"] = 0
        if not mentioned_labels:
            mentioned_labels = ["other_platform"]

        return {
            "primary_labels": primary_labels,
            "mentioned_labels": mentioned_labels,
            "secondary_labels": secondary_labels,
            "scores": scores,
        }

    def _classify_generic_group(self, title: str, transcript_text: str, hook_text: str, group_name: str, fallback_label: str) -> dict:
        result = self._score_group(
            title,
            transcript_text,
            hook_text,
            self.taxonomy.get(group_name, {}),
        )
        scores = result["scores"]
        title_hits = result["title_hits"]
        hook_hits = result["hook_hits"]

        labels = []
        for label in self._sorted_labels(scores):
            has_strong_signal = (
                title_hits.get(label, 0) > 0
                or hook_hits.get(label, 0) > 0
                or scores[label] >= 2
            )
            if has_strong_signal:
                labels.append(label)

        if not labels:
            labels = [fallback_label]
            scores[fallback_label] = 0

        return {
            "labels": labels,
            "scores": scores,
        }

    def classify_video(self, title: str, transcript_text: str, hook_text: str) -> dict:
        platform_result = self._classify_platforms(title, transcript_text, hook_text)
        format_result = self._classify_generic_group(
            title,
            transcript_text,
            hook_text,
            "formats",
            "other_format",
        )
        hook_result = self._classify_generic_group(
            title,
            transcript_text,
            hook_text,
            "hooks",
            "other_hook",
        )

        confidence_denominator = (
            max(1, len(platform_result["primary_labels"]))
            + max(1, len(format_result["labels"]))
            + max(1, len(hook_result["labels"]))
        )
        confidence_numerator = (
            sum(platform_result["scores"].get(label, 0) for label in platform_result["primary_labels"])
            + sum(format_result["scores"].get(label, 0) for label in format_result["labels"])
            + sum(hook_result["scores"].get(label, 0) for label in hook_result["labels"])
        )

        return {
            "platform_labels": platform_result["primary_labels"],
            "mentioned_platform_labels": platform_result["mentioned_labels"],
            "secondary_platform_labels": platform_result["secondary_labels"],
            "format_labels": format_result["labels"],
            "hook_labels": hook_result["labels"],
            "platform_scores": platform_result["scores"],
            "format_scores": format_result["scores"],
            "hook_scores": hook_result["scores"],
            "confidence_score": round(confidence_numerator / confidence_denominator, 2),
        }
