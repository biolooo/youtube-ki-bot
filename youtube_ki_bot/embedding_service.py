import math


class EmbeddingService:
    def __init__(self, api_key=None, model="text-embedding-3-small"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY fehlt.")
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImportError("Package 'openai' ist nicht installiert.") from exc
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    @staticmethod
    def build_embedding_text(reference: dict) -> str:
        return "\n".join(
            [
                f"Title: {reference.get('title', '')}",
                f"Hook: {reference.get('hook_text', '')}",
                f"Platforms: {', '.join(reference.get('platform_labels', []))}",
                f"Formats: {', '.join(reference.get('format_labels', []))}",
                f"Hooks: {', '.join(reference.get('hook_labels', []))}",
                f"Transcript: {reference.get('transcript_text', '')}",
            ]
        ).strip()

    def embed_texts(self, texts: list) -> list:
        client = self._get_client()
        response = client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    @staticmethod
    def cosine_similarity(vector_a: list, vector_b: list) -> float:
        if not vector_a or not vector_b:
            return 0.0
        dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
        norm_a = math.sqrt(sum(a * a for a in vector_a))
        norm_b = math.sqrt(sum(b * b for b in vector_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)
