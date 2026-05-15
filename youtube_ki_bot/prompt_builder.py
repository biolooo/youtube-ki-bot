from collections import Counter

from youtube_ki_bot.text_utils import extract_top_terms, split_sentences, tokenize_words


CHANNEL_STYLE_RULES = [
    "Schreibe natuerliches, direktes, alltagssprachliches Deutsch.",
    "Klinge wie ein echter Creator, nicht wie ein Marketing-Texter.",
    "Halte Saetze kurz, konkret und sprechbar.",
    "Die Hook muss in den ersten 1-2 Saetzen Neugier, Reibung oder klaren Nutzen erzeugen.",
    "Der Hauptteil soll schnell auf den Punkt kommen und keine langen Einleitungen haben.",
    "Wenn passend, nutze leichte Reibung, klare Meinung oder konkrete Beobachtung statt weichgespuelter Aussagen.",
]

ANTI_PATTERNS = [
    "Keine leeren Floskeln wie 'Heute reden wir ueber', 'In diesem Video' oder 'lass uns einen Blick darauf werfen'.",
    "Keine sterile Hochsprache und kein Agentur-Sprech.",
    "Keine generischen 3-Punkte-Listen, wenn die Referenzen eher story- oder meinungsgetrieben sind.",
    "Keine Wiederholung der Hook als erster Satz ohne neue Information.",
    "Keine Emojis oder Hashtags im Script.",
]

FORMAT_GUIDANCE = {
    "buying_advice": [
        "Stelle schnell klar, fuer wen sich das Produkt lohnt und fuer wen nicht.",
        "Nutze 2-4 greifbare Kaufargumente oder Kaufwarnungen.",
        "Baue einen glaubwuerdigen Reality-Check ein, damit es nicht wie Werbung klingt.",
    ],
    "tutorial_guide": [
        "Fokussiere dich auf ein konkretes Problem und die schnellste Loesung.",
        "Sprich in kurzen Handlungsschritten oder einer sehr klaren Abfolge.",
        "Die Hook darf das Problem zuspitzen, der Hauptteil muss dann sofort Nutzen liefern.",
    ],
    "technical_modding": [
        "Betone Nutzen, Risiko oder Aha-Effekt des Mods.",
        "Nutze Fachbegriffe nur, wenn sie fuer die Zielgruppe normal sind.",
        "Kombiniere technischen Mehrwert mit einer klaren Meinung oder starken Beobachtung.",
    ],
    "order_packaging": [
        "Fokussiere auf Kundenmoment, Produktfreude und konkrete Details im Paket.",
        "Nutze persoenliche Ansprache und kleine storyhafte Beobachtungen.",
    ],
    "opinion_hot_take": [
        "Die Hook braucht eine klare, zugespitzte Meinung oder Reibung.",
        "Begruende die These mit 2-3 schnellen Punkten, statt drumherum zu reden.",
    ],
    "retro_nostalgia": [
        "Mische Gefuehl, Erinnerung und einen klaren Grund, warum das Thema heute noch relevant ist.",
        "Nutze keine kitschige Nostalgie-Sprache, sondern konkrete Beispiele.",
    ],
}

HOOK_GUIDANCE = {
    "question_hook": "Die Hook soll als klare, starke Frage formuliert sein, die sofort eine Meinung oder Kaufentscheidung triggert.",
    "controversy_hook": "Die Hook soll eine kontroverse, reibende oder polarisierende Behauptung enthalten.",
    "problem_solution": "Die Hook soll ein konkretes Problem ansprechen und direkt Loesungsneugier erzeugen.",
    "direct_address": "Die Hook soll den Zuschauer direkt ansprechen und persoenlich wirken.",
    "customer_story": "Die Hook soll wie ein echter kleiner Kunden- oder Creator-Moment wirken.",
}


def _clip(text: str, max_length: int = 240) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1] + "…"


def _extract_opening_lines(transcript_text: str, max_sentences: int = 3) -> list[str]:
    return split_sentences(transcript_text or "")[:max_sentences]


def _extract_cta_hint(transcript_text: str) -> str:
    sentences = split_sentences(transcript_text or "")
    if not sentences:
        return ""
    tail = sentences[-3:]
    question_sentence = next((sentence for sentence in reversed(tail) if "?" in sentence), "")
    if question_sentence:
        return _clip(question_sentence, 180)
    cta_sentence = next(
        (
            sentence for sentence in reversed(tail)
            if any(
                marker in sentence.lower()
                for marker in ["kommentar", "schreib", "sag", "folgen", "abo", "like"]
            )
        ),
        "",
    )
    return _clip(cta_sentence, 180)


def _extract_reference_summary(reference: dict) -> str:
    transcript_text = reference.get("transcript_text", "")
    openings = _extract_opening_lines(transcript_text, max_sentences=2)
    opening_text = " / ".join(_clip(sentence, 140) for sentence in openings if sentence)
    cta_hint = _extract_cta_hint(transcript_text)
    summary_parts = []
    if opening_text:
        summary_parts.append(f"Einstieg: {opening_text}")
    if cta_hint:
        summary_parts.append(f"CTA-Tendenz: {cta_hint}")
    if reference.get("hook_text"):
        summary_parts.append(f"Hook: {_clip(reference['hook_text'], 160)}")
    return " | ".join(summary_parts)


def _describe_reference(item: dict) -> str:
    reference = item["reference"]
    summary = _extract_reference_summary(reference)
    return "\n".join(
        [
            f"- Titel: {reference.get('title', '')}",
            f"  Views: {reference.get('views', 0)} | Score: {item.get('score', 0)}",
            f"  Plattformen: {', '.join(reference.get('platform_labels', [])) or 'keine'}",
            f"  Formate: {', '.join(reference.get('format_labels', [])) or 'keine'}",
            f"  Hooks: {', '.join(reference.get('hook_labels', [])) or 'keine'}",
            f"  Kurzprofil: {summary or 'keine Zusammenfassung'}",
        ]
    )


def _build_pattern_summary(retrieval_results: list) -> str:
    references = [item["reference"] for item in retrieval_results]
    hook_labels = Counter()
    format_labels = Counter()
    opening_terms = []
    cta_hints = []

    for reference in references:
        hook_labels.update(reference.get("hook_labels", []))
        format_labels.update(reference.get("format_labels", []))
        opening_text = " ".join(_extract_opening_lines(reference.get("transcript_text", ""), max_sentences=2))
        if opening_text:
            opening_terms.append(opening_text)
        cta_hint = _extract_cta_hint(reference.get("transcript_text", ""))
        if cta_hint:
            cta_hints.append(cta_hint)

    top_terms = extract_top_terms(opening_terms, limit=8)
    top_words = ", ".join(term["term"] for term in top_terms[:6]) or "keine"
    top_hooks = ", ".join(label for label, _ in hook_labels.most_common(4)) or "keine"
    top_formats = ", ".join(label for label, _ in format_labels.most_common(4)) or "keine"
    cta_summary = "; ".join(_clip(item, 110) for item in cta_hints[:3]) or "keine klare CTA-Tendenz"

    return "\n".join(
        [
            f"- Dominante Hook-Muster: {top_hooks}",
            f"- Dominante Formate: {top_formats}",
            f"- Auffaellige Einstiegsbegriffe: {top_words}",
            f"- CTA-Tendenzen: {cta_summary}",
        ]
    )


class PromptBuilder:
    def build(self, brief: str, retrieval_results: list, platform: str = None, format_label: str = None, hook_label: str = None) -> str:
        format_rules = FORMAT_GUIDANCE.get(format_label or "", [])
        hook_rule = HOOK_GUIDANCE.get(hook_label or "", "")
        references_section = "\n\n".join(_describe_reference(item) for item in retrieval_results[:5])
        pattern_summary = _build_pattern_summary(retrieval_results)
        format_section = "\n".join(f"- {rule}" for rule in format_rules) or "- Keine spezielle Formatregel vorgegeben."
        style_section = "\n".join(f"- {rule}" for rule in CHANNEL_STYLE_RULES)
        anti_section = "\n".join(f"- {rule}" for rule in ANTI_PATTERNS)
        output_contract = "\n".join(
            [
                "- Antworte nur als JSON-Objekt.",
                "- title_ideas: Array mit 4 bis 6 deutschen Titelideen.",
                "- hook: 1-2 kurze Saetze als starker Einstieg.",
                "- script: kompletter Short-Text in natuerlicher Sprechsprache, ohne Ueberschriften.",
                "- cta: ein konkreter kurzer Abschluss mit Kommentar- oder Reaktionsanreiz.",
                "- why_this_should_work: Array mit 3 bis 5 kurzen Punkten.",
            ]
        )

        return (
            "Du bist ein deutscher YouTube-Shorts-Creator fuer Gaming-, Retro- und Tech-Content. "
            "Dein Job ist nicht, generische Marketingtexte zu schreiben, sondern ein Script, das "
            "wie ein echter starker Short klingt.\n\n"
            "Ziel:\n"
            f"- Plattform: {platform or 'offen'}\n"
            f"- Format: {format_label or 'offen'}\n"
            f"- Hook-Typ: {hook_label or 'offen'}\n"
            f"- Briefing:\n{brief}\n\n"
            "Kanal-Stilregeln:\n"
            f"{style_section}\n\n"
            "Format-Regeln:\n"
            f"{format_section}\n\n"
            "Hook-Regel:\n"
            f"- {hook_rule or 'Kein spezieller Hook-Zwang, aber der Einstieg muss stark sein.'}\n\n"
            "Was du vermeiden musst:\n"
            f"{anti_section}\n\n"
            "Muster aus erfolgreichen Referenzen:\n"
            f"{pattern_summary}\n\n"
            "Beste Referenzen:\n"
            f"{references_section}\n\n"
            "Wichtige Arbeitsweise:\n"
            "- Nutze die Referenzen fuer Sprachgefuehl, Tempo, Hook-Mechanik und CTA-Logik.\n"
            "- Kopiere keine Formulierungen woertlich.\n"
            "- Wenn die Referenzen eher meinungsstark und direkt sind, schreibe auch direkt.\n"
            "- Wenn ein Punkt unklar ist, entscheide dich fuer die konkretere und sprechbarere Version.\n"
            "- Das Script soll sich anfuehlen, als koennte man es sofort vor der Kamera sagen.\n\n"
            "Ausgabeformat:\n"
            f"{output_contract}"
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
