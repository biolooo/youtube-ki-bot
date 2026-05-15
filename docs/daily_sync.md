# Daily Sync

## Ziel

Der Tageslauf soll drei Dinge in einem Schritt erledigen:

1. den Kanal auf neue Videos prüfen
2. `views`, `likes` und `comments` für alle bekannten Videos aktualisieren
3. maximal eine kleine Anzahl fehlender Shorts transkribieren und analysieren

## Command

```bash
./venv/bin/python main.py daily-sync
```

Standardmäßig verarbeitet der Lauf höchstens `5` fehlende Shorts. Der Wert kommt aus:

```env
SYNC_MAX_SHORTS_PER_RUN=5
```

Optional kann der Wert pro Ausführung überschrieben werden:

```bash
./venv/bin/python main.py daily-sync --limit 3
```

## Ablauf

Bei jedem Lauf passiert:

1. kompletter YouTube-Kanal-Scan
2. Aktualisierung aller Video-Metadaten in `videos`
3. Erkennung neuer Shorts
4. Auswahl fehlender Shorts ohne Analyse
5. Priorisierung:
   - neue Shorts zuerst
   - danach bereits bekannte, aber noch nicht analysierte Shorts
6. Verarbeitung von maximal `SYNC_MAX_SHORTS_PER_RUN` Shorts
7. Rebuild von Referenzgruppen und fehlenden Embeddings

## Railway

Der Python-Code selbst startet keinen internen Scheduler. Der empfohlene Produktionsweg ist ein täglicher Railway-Job, der genau diesen Command ausführt:

```bash
python main.py daily-sync
```

So bleibt der Lauf:

- idempotent
- leicht testbar
- unabhängig vom Webprozess
