from youtube_ki_bot.embedding_service import EmbeddingService
from youtube_ki_bot.text_utils import normalize_for_matching


class RetrievalService:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    @staticmethod
    def _keyword_overlap_score(query_text: str, reference: dict) -> float:
        normalized_query = normalize_for_matching(query_text)
        if not normalized_query:
            return 0.0
        haystack = normalize_for_matching(
            " ".join(
                [
                    reference.get("title", ""),
                    reference.get("hook_text", ""),
                    " ".join(reference.get("platform_labels", [])),
                    " ".join(reference.get("format_labels", [])),
                    " ".join(reference.get("hook_labels", [])),
                    reference.get("transcript_text", "")[:600],
                ]
            )
        )
        query_terms = [term for term in normalized_query.split() if len(term) > 2]
        if not query_terms:
            return 0.0
        hits = sum(1 for term in query_terms if term in haystack)
        return hits / len(query_terms)

    @staticmethod
    def _metadata_filter_score(reference: dict, platform=None, format_label=None, hook_label=None) -> float:
        score = 0.0
        if platform:
            if platform in reference.get("platform_labels", []):
                score += 2.0
            elif platform in reference.get("mentioned_platform_labels", []):
                score += 0.75
        if format_label and format_label in reference.get("format_labels", []):
            score += 2.0
        if hook_label and hook_label in reference.get("hook_labels", []):
            score += 1.5
        return score

    @staticmethod
    def _performance_score(reference: dict) -> float:
        top_bonus = 1.5 if reference.get("is_top_reference") else 0.0
        confidence_bonus = min(reference.get("taxonomy_confidence_score", 0) / 3.0, 2.0)
        like_bonus = min(reference.get("like_rate", 0) * 100, 2.0)
        comment_bonus = min(reference.get("comment_rate", 0) * 200, 1.5)
        views_bonus = min(reference.get("views", 0) / 100000, 3.0)
        return top_bonus + confidence_bonus + like_bonus + comment_bonus + views_bonus

    def build_embedding_index(self, references: list) -> dict:
        texts = [self.embedding_service.build_embedding_text(reference) for reference in references]
        vectors = self.embedding_service.embed_texts(texts)
        return {
            "model": self.embedding_service.model,
            "items": [
                {
                    "video_id": reference["video_id"],
                    "embedding": vector,
                }
                for reference, vector in zip(references, vectors)
            ],
        }

    @staticmethod
    def _index_by_video_id(embedding_index: dict) -> dict:
        items = embedding_index.get("items", []) if embedding_index else []
        return {item["video_id"]: item["embedding"] for item in items}

    def retrieve(
        self,
        references: list,
        query_text: str = "",
        platform: str = None,
        format_label: str = None,
        hook_label: str = None,
        top_k: int = 5,
        embedding_index: dict = None,
    ) -> list:
        embedding_lookup = self._index_by_video_id(embedding_index) if embedding_index else {}
        query_embedding = None
        if query_text and embedding_index and self.embedding_service.is_available():
            query_embedding = self.embedding_service.embed_texts([query_text])[0]

        scored_results = []
        for reference in references:
            metadata_score = self._metadata_filter_score(reference, platform, format_label, hook_label)
            keyword_score = self._keyword_overlap_score(query_text, reference)
            performance_score = self._performance_score(reference)
            semantic_score = 0.0

            if query_embedding is not None:
                reference_embedding = embedding_lookup.get(reference["video_id"])
                semantic_score = self.embedding_service.cosine_similarity(
                    query_embedding,
                    reference_embedding,
                )

            total_score = (
                metadata_score * 3.0
                + keyword_score * 2.0
                + semantic_score * 4.0
                + performance_score
            )
            scored_results.append(
                {
                    "score": round(total_score, 4),
                    "metadata_score": round(metadata_score, 4),
                    "keyword_score": round(keyword_score, 4),
                    "semantic_score": round(semantic_score, 4),
                    "performance_score": round(performance_score, 4),
                    "reference": reference,
                }
            )

        scored_results.sort(key=lambda item: item["score"], reverse=True)
        return scored_results[:top_k]
