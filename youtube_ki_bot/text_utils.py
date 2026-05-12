import re
from collections import Counter


GERMAN_STOPWORDS = {
    "aber", "als", "am", "an", "auch", "auf", "aus", "bei", "bin", "bis", "bist",
    "da", "das", "dass", "dein", "deine", "dem", "den", "der", "des", "die", "dir",
    "doch", "du", "ein", "eine", "einer", "einem", "einen", "er", "es", "für", "hat",
    "hier", "ich", "ihr", "ihn", "im", "in", "ist", "ja", "jetzt", "kann", "klar",
    "mit", "nach", "nein", "nicht", "noch", "nur", "oder", "schon", "sehr", "sein",
    "sich", "sie", "sind", "so", "und", "uns", "unser", "von", "war", "was", "wenn",
    "wie", "wir", "wird", "wo", "zu", "zum", "zur",
}

HOOK_TRIGGER_WORDS = {
    "warum", "dieser", "diese", "sony", "trick", "kostenlos", "perfekt", "klar",
    "danke", "hast", "kannst", "welche", "viel spass", "viel spaß",
}


def iso8601_duration_to_seconds(duration: str) -> int:
    pattern = re.compile(
        r"^P"
        r"(?:(?P<days>\d+)D)?"
        r"(?:T"
        r"(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?"
        r"(?:(?P<seconds>\d+)S)?"
        r")?$"
    )
    match = pattern.match(duration)
    if not match:
        raise ValueError(f"Unbekanntes Dauerformat: {duration}")
    parts = {name: int(value or 0) for name, value in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def chunked(items, chunk_size):
    for start in range(0, len(items), chunk_size):
        yield items[start:start + chunk_size]


def flatten_transcript_segments(segments) -> str:
    return " ".join(
        segment.get("text", "").strip()
        for segment in segments
        if segment.get("text", "").strip()
    ).strip()


def split_sentences(text: str) -> list:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def normalize_for_matching(text: str) -> str:
    text = text.lower().replace("ß", "ss")
    text = re.sub(r"[^a-z0-9äöü\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize_words(text: str) -> list:
    return re.findall(r"[a-zA-ZäöüÄÖÜß0-9]+", text.lower())


def extract_hook_text(title: str, transcript_text: str) -> str:
    sentences = split_sentences(transcript_text)
    if sentences:
        return sentences[0]
    return title.strip()


def extract_top_terms(texts, limit: int = 15) -> list:
    counter = Counter()
    for text in texts:
        for word in tokenize_words(text):
            if len(word) < 3 or word in GERMAN_STOPWORDS:
                continue
            counter[word] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def extract_top_bigrams(texts, limit: int = 10) -> list:
    counter = Counter()
    for text in texts:
        words = [
            word for word in tokenize_words(text)
            if len(word) >= 3 and word not in GERMAN_STOPWORDS
        ]
        for first, second in zip(words, words[1:]):
            counter[f"{first} {second}"] += 1
    return [{"bigram": bigram, "count": count} for bigram, count in counter.most_common(limit)]
