# UI Flow

## Ziel

Die spaetere Eingabe soll nicht aus einem einzigen freien Prompt bestehen. Nutzer sollen in wenigen klaren Feldern angeben koennen, was sie wollen, waehrend das System daraus intern einen strukturierten Request baut.

## Empfohlener Flow

### 1. Einstieg

Screen: `Neues Script erstellen`

Felder:

- Thema
- Plattform
- Video-Art
- Hook-Art
- Ziel des Videos
- Ton/Stil
- Ziellaenge
- Besondere Vorgaben
- optionale freie Idee

### 2. Vorschau des Retrievals

Screen: `Passende Vorbilder`

Anzeigen:

- Top-Referenzen
- Titel
- Hook
- Plattform / Format / Hook-Typ
- Views
- kurzer Grund, warum das Video ausgewaehlt wurde

Ziel:

- der Nutzer versteht, auf welchen Vorbildern die KI aufsetzt

### 3. Generierung

Screen: `Script-Varianten`

Anzeigen:

- 2 bis 3 Script-Varianten
- Hook
- kompletter Scripttext
- CTA
- verwendete Referenzen

### 4. Entscheidung

Aktionen:

- Variante uebernehmen
- Variante neu schreiben
- weitere Variante erzeugen
- Referenzen neu auswaehlen

### 5. Feedback

Optional spaeter:

- hilfreich / nicht hilfreich
- zu generisch
- zu lang
- falscher Stil
- falsche Plattform / falsches Format

Dieses Feedback sollte gespeichert werden, damit das Retrieval spaeter besser gewichtet werden kann.

## Minimales internes Request-Modell

Die UI sollte spaeter ein strukturiertes Objekt an die API schicken:

- `topic`
- `platform`
- `format_label`
- `hook_label`
- `goal`
- `tone`
- `target_length_seconds`
- `constraints`
- `freeform_brief`
- `top_k`

## Warum dieser Flow sinnvoll ist

- der Nutzer muss kein Prompt-Profi sein
- das System kann stabiler passende Referenzen holen
- spaeter koennen Eingabe, Retrieval und Ausgabe getrennt verbessert werden
