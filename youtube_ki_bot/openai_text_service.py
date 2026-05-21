import json


class OpenAITextService:
    def __init__(self, api_key=None, model="gpt-4o-mini"):
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

    def polish_text(self, text: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein Lektor. Korrigiere ausschließlich Rechtschreibung, "
                        "Grammatik und Zeichensetzung. Behalte Stil, Tonalität, Stichpunkte, "
                        "Absätze und Bedeutung exakt bei. Antworte ausschließlich mit dem "
                        "korrigierten Text, ohne Kommentar."
                    ),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def extract_topic_suggestion(self, title: str, transcript_text: str, views: int, last_used_at: str = "") -> dict:
        client = self._get_client()
        prompt = (
            "Extrahiere aus Titel und Transcript ein erfolgreich klingendes YouTube-Short-Thema. "
            "Thema maximal 90 Zeichen. Formuliere außerdem genau einen kurzen Satz als Begründung. "
            "Die Begründung soll den Erfolg und die lange Nicht-Nutzung knapp einordnen. "
            "Antworte nur als JSON mit den Feldern topic und reason.\n\n"
            f"Titel: {title}\n"
            f"Views: {views}\n"
            f"Last used at: {last_used_at or 'nie'}\n"
            f"Transcript:\n{transcript_text[:2500]}"
        )
        response = client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        content = (response.choices[0].message.content or "").strip()
        return self._extract_json_payload(content)

    def distill_hook(self, transcript_text: str) -> str:
        client = self._get_client()
        prompt = (
            "Extrahiere die erste starke Hook-Line aus diesem Transcript. "
            "Maximal 140 Zeichen. Nur die Hook-Line, keine Erklärung.\n\n"
            f"{transcript_text[:2000]}"
        )
        response = client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return (response.choices[0].message.content or "").strip()

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
