import json

from youtube_ki_bot.prompt_builder import PromptBuilder


class ScriptGenerationService:
    def __init__(self, api_key=None, model="gpt-5.5"):
        self.api_key = api_key
        self.model = model
        self._client = None
        self.prompt_builder = PromptBuilder()

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

    def generate_script(
        self,
        brief: str,
        retrieval_results: list,
        platform: str = None,
        format_label: str = None,
        hook_label: str = None,
    ) -> dict:
        client = self._get_client()
        prompt = self.prompt_builder.build(
            brief=brief,
            retrieval_results=retrieval_results,
            platform=platform,
            format_label=format_label,
            hook_label=hook_label,
        )
        response = client.responses.create(
            model=self.model,
            input=prompt,
        )
        raw_payload = self._extract_json_payload(response.output_text)
        return self.prompt_builder.normalize_payload(raw_payload)

    @staticmethod
    def _extract_json_payload(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(cleaned[start:end + 1])
