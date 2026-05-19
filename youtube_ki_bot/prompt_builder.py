def _clip(text: str, max_length: int = 2200) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1] + "…"


class PromptBuilder:
    @staticmethod
    def _build_reference_texts(retrieval_results: list) -> str:
        blocks = []
        for index, item in enumerate(retrieval_results[:5], start=1):
            reference = item["reference"]
            transcript_text = reference.get("transcript_text", "").strip()
            fallback_text = reference.get("hook_text", "").strip()
            style_text = transcript_text or fallback_text or reference.get("title", "")
            blocks.append(
                "\n".join(
                    [
                        f"Referenztext {index}:",
                        f"Titel: {reference.get('title', '')}",
                        _clip(style_text),
                    ]
                )
            )
        return "\n\n".join(blocks)

    def build(
        self,
        brief: str,
        retrieval_results: list,
        platform: str = None,
        format_label: str = None,
        hook_label: str = None,
    ) -> str:
        reference_texts = self._build_reference_texts(retrieval_results)
        return (
            "Schreibe ein Video mit diesem Inhalt:\n\n"
            f"{brief}\n\n"
            "Oben habe ich dir inhaltlich eine grobe Idee gegeben. "
            "Formuliere daraus einen Fliesstext. "
            "Orientiere dich bezueglich des Stils an diesen Referenztexten. "
            "Versuche moeglichst nahe an der Referenz zu bleiben, was Ton und Feeling angeht.\n\n"
            f"{reference_texts}\n\n"
            "Wichtig:\n"
            "- Nutze die Referenztexte als Stilvorlage fuer Ton, Satzbau, Energie und Gefuehl.\n"
            "- Kopiere keine Saetze woertlich.\n"
            "- Der Text soll sich wie ein echter gesprochener YouTube-Short anfuehlen.\n"
            "- Kein Meta-Kommentar ueber den Schreibprozess.\n"
            "- Keine Einleitung wie 'Hier ist dein Script'.\n\n"
            "Gib die Antwort nur als JSON-Objekt mit diesen Feldern zurueck:\n"
            "- title_ideas: Array mit 4 bis 6 Titelideen\n"
            "- hook: starker Einstieg in 1 bis 2 Saetzen\n"
            "- script: kompletter Fliesstext fuer das Video\n"
            "- cta: kurzer Abschluss oder Call to Action\n"
            "- why_this_should_work: Array mit 3 bis 5 kurzen Gruenden\n\n"
            "Sage mir nicht extra, dass du fertig bist. Antworte nur mit dem JSON."
        )

    @staticmethod
    def normalize_payload(payload: dict) -> dict:
        title_ideas = payload.get("title_ideas", [])
        if isinstance(title_ideas, str):
            title_ideas = [item.strip() for item in title_ideas.split("\n") if item.strip()]
        title_ideas = [str(item).strip() for item in title_ideas if str(item).strip()]

        why = payload.get("why_this_should_work", [])
        if isinstance(why, str):
            parts = [part.strip(" -•\t") for part in why.split("\n") if part.strip()]
            if not parts:
                parts = [why.strip()]
            why = parts
        why = [str(item).strip() for item in why if str(item).strip()]

        return {
            "title_ideas": title_ideas[:6],
            "hook": str(payload.get("hook", "") or "").strip(),
            "script": str(payload.get("script", "") or "").strip(),
            "cta": str(payload.get("cta", "") or "").strip(),
            "why_this_should_work": why[:5],
        }
