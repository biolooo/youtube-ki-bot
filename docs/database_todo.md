# Database ToDo

## Ziel

Die Pipeline soll nicht mehr nur lokal mit CSV- und JSON-Dateien arbeiten. Relevante Daten sollen in einer Datenbank liegen, damit:

- API und Frontend stabil darauf zugreifen koennen
- neue Videos spaeter einzeln nachgeladen werden koennen
- View-Counts spaeter aktualisiert und neu bewertet werden koennen
- generierte Scripts, Requests und Referenzen dauerhaft nachvollziehbar bleiben

## Priorisierte Schritte

1. Health-Debug wieder entfernen
2. Datenbank-Ziel festziehen
   - bevorzugt `Supabase/Postgres`
3. Datenmodell finalisieren
   - auf Basis von [supabase_schema.sql](/Users/maximneumann/Desktop/youtube_ki_bot/docs/supabase_schema.sql:1)
4. Datenbank-Konfiguration ins Backend aufnehmen
   - URL/Keys/Schalter per Env
5. Kleine Datenbank-Schicht einfuehren
   - getrennt von CSV/JSON-Storage
6. Referenzbibliothek aus DB lesbar machen
   - zunaechst nur Lesen
7. Import-Skript bauen
   - aktuelle `reference_library.json`
   - `embedding_index.json`
   - Analyse-/Video-Daten
8. API-Requests und generierte Scripts in DB speichern
9. Endpunkt oder Job fuer einzelnes Video-Nachladen definieren
10. Endpunkt oder Job fuer periodische View-Updates definieren
11. Ranking/Top-Referenzen auf neue View-Daten anpassbar machen
12. Spaeter Embeddings direkt in DB (`pgvector`) verwalten

## Empfohlene Reihenfolge

### Phase 1: DB-Basis

- DB-Zugang konfigurieren
- Lese-/Schreibschicht anlegen
- bestehende Daten importieren

### Phase 2: API-Persistenz

- Generation Requests speichern
- generierte Scripts speichern
- Referenzverwendungen speichern

### Phase 3: Video-Lifecycle

- einzelne Videos nachladen
- Views aktualisieren
- Reanalyse gezielt fuer geaenderte Videos

## Naechster konkreter Schritt

Der erste DB-Schritt nach dieser Liste ist:

- Datenbank-Konfiguration und eine kleine Python-DB-Schicht vorbereiten

Damit koennen wir danach gezielt Import und Persistenz anbinden, ohne den Rest der App umzubauen.
