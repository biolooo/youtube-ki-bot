# Lovable Connection Test

## Ziel

Dieses Projekt stellt jetzt eine HTTP-API bereit, die von Lovable angesprochen werden kann.

## Voraussetzungen

- `reference_library.json` vorhanden
- `embedding_index.json` vorhanden
- `OPENAI_API_KEY` in `.env`

## Backend lokal starten

```bash
./venv/bin/python -m uvicorn youtube_ki_bot.api_app:app --host 0.0.0.0 --port 8000 --reload
```

## Test-Endpunkte

### Health

```bash
curl http://127.0.0.1:8000/health
```

### Referenzen abrufen

```bash
curl -X POST http://127.0.0.1:8000/retrieve-references \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "Nintendo 3DS lohnt sich heute noch",
    "platform": "nintendo_3ds",
    "format_label": "buying_advice",
    "hook_label": "question_hook",
    "top_k": 5
  }'
```

### Script erzeugen

```bash
curl -X POST http://127.0.0.1:8000/generate-script \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Warum sich ein Nintendo 3DS heute noch lohnt",
    "platform": "nintendo_3ds",
    "format_label": "buying_advice",
    "hook_label": "question_hook",
    "goal": "Kommentare und Kaufinteresse erzeugen",
    "tone": "locker, direkt, deutsch",
    "target_length_seconds": 40,
    "constraints": "keine leeren Marketing-Floskeln",
    "freeform_brief": "Der Zuschauer soll verstehen, warum der 3DS auch heute noch spannend ist.",
    "top_k": 5
  }'
```

## Lovable

Lovable kann laut offizieller Doku:

- mit Supabase verbunden werden
- Build-Flows ueber die Lovable API ausloesen
- externe APIs aus Frontend/Backend-Flows ansprechen

Relevante Doku:

- Lovable API: https://docs.lovable.dev/integrations/lovable-api
- Supabase Integration: https://docs.lovable.dev/integrations/supabase

## Empfehlung fuer den Test

In Lovable zuerst eine kleine interne App bauen mit:

1. Formular fuer `topic`, `platform`, `format_label`, `hook_label`, `goal`, `tone`
2. `POST` auf `/generate-script`
3. Ausgabe von:
   - `script_payload.title_ideas`
   - `script_payload.hook`
   - `script_payload.script`
   - `script_payload.cta`

## CORS

Standardmaessig ist `API_ALLOWED_ORIGINS=*`.

Spaeter enger setzen, zum Beispiel:

```bash
API_ALLOWED_ORIGINS=https://your-lovable-app-domain.com
```
