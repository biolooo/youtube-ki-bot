# App Architecture

## Ziel

Dieses Projekt soll von einer reinen Analyse-Pipeline zu einem nutzerfreundlichen KI-System werden, das:

- eine strukturierte Nutzereingabe annimmt
- passende Referenzvideos aus dem Bestand auswählt
- daraus neue YouTube-Short-Scripts erzeugt
- Anfragen, Referenzen und Ergebnisse dauerhaft speichert

## Empfehlung

Empfohlene Architektur fuer den naechsten Ausbauschritt:

1. Supabase als zentrale Datenbank
2. schlankes API-Layer vor den bestehenden Python-Services
3. erste UI mit Lovable oder einem anderen Frontend, das gegen die API arbeitet

Diese Aufteilung ist bewusst getrennt:

- `Database`: langfristige Datenhaltung
- `API`: Business-Logik und KI-Orchestrierung
- `UI`: nutzerfreundliche Eingabe und Ausgabe

## Optionen

### Option A: Lovable + Supabase + eigene API

Gut fuer:

- schnelle erste Produktoberflaeche
- eigenes Branding
- spaetere Weiterentwicklung zu einer echten App

Nachteile:

- Frontend ist schnell erstellt, aber Backend-Vertraege muessen trotzdem sauber sein
- KI-generierte UI-Strukturen brauchen oft spaeter Aufraeumarbeit

### Option B: Retool + Supabase + eigene API

Gut fuer:

- internes Tool
- schnelles Testen des End-to-End-Flows
- administrative Oberflaechen

Nachteile:

- weniger produktartig
- weniger geeignet fuer spaeteres externes Nutzererlebnis

### Option C: Bestehendes System mit Datenbank-Anbindung

Gut fuer:

- wenn bereits ein stabiles Tool fuer Formulare, User-Management oder Workflows existiert

Nachteile:

- mehr Schnittstellenkoordination
- Gefahr, dass die eigentliche KI-Logik auf mehrere Systeme verteilt wird

## Empfohlener Weg

### Phase 1

- Supabase-Schema aufsetzen
- bestehende JSON/CSV-Daten in eine relationale Struktur ueberfuehren
- API-Vertrag fuer Retrieval und Script-Generierung festlegen

### Phase 2

- strukturierte Eingabeoberflaeche bauen
- erste interne Version mit Lovable oder Retool testen
- Requests und Ergebnisse persistieren

### Phase 3

- Feedback-Schleife einbauen
- mehrere Script-Varianten erzeugen
- spaeter Bewertungsdaten zur Optimierung des Retrievals nutzen

## API-Verantwortung

Die API sollte spaeter mindestens diese Aufgaben uebernehmen:

- Eingabe validieren
- Retrieval-Request aufbauen
- passende Referenzen auswaehlen
- KI-Prompt/Context erzeugen
- Script generieren
- Anfrage, Referenzen und Ergebnis speichern

## UI-Verantwortung

Die UI sollte spaeter nur diese Aufgaben haben:

- Nutzereingabe sammeln
- Ergebnisse anzeigen
- Varianten vergleichen
- ggf. Feedback oder Freigaben erfassen

Die eigentliche Auswahl- und KI-Logik sollte nicht im Frontend liegen.
