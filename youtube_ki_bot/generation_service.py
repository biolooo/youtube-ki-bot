import json


class ScriptGenerationService:
    def __init__(self, api_key=None, model="gpt-5.5"):
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
    def build_reference_payload(retrieval_results: list) -> list:
        payload = []
        for item in retrieval_results:
            reference = item["reference"]
            payload.append(
                {
                    "score": item["score"],
                    "title": reference["title"],
                    "hook_text": reference["hook_text"],
                    "platform_labels": reference["platform_labels"],
                    "format_labels": reference["format_labels"],
                    "hook_labels": reference["hook_labels"],
                    "views": reference["views"],
                    "transcript_text": reference["transcript_text"][:1600],
                }
            )
        return payload

    def generate_script(
        self,
        brief: str,
        retrieval_results: list,
        platform: str = None,
        format_label: str = None,
        hook_label: str = None,
    ) -> str:
        client = self._get_client()
        reference_payload = self.build_reference_payload(retrieval_results)
        prompt = (
            "Du schreibst ein neues YouTube-Short-Script auf Basis erfolgreicher Referenzen.\n"
            "Nutze die Referenzen als Stil- und Strukturvorlage, kopiere aber nichts wörtlich.\n"
            "Gib die Antwort als JSON mit den Feldern "
            "`title_ideas`, `hook`, `script`, `cta`, `why_this_should_work` zurück.\n\n"
            f"Zielplattform: {platform or 'offen'}\n"
            f"Zielformat: {format_label or 'offen'}\n"
            f"Zielhook: {hook_label or 'offen'}\n"
            f"Briefing: {brief}\n\n"
            f"Referenzen:\n{json.dumps(reference_payload, ensure_ascii=False, indent=2)}"
        )
        response = client.responses.create(
            model=self.model,
            input=prompt,
        )
        return response.output_text
