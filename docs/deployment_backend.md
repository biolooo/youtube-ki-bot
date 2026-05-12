# Backend Deployment

## Ziel

Das API-Backend soll nicht mehr ueber einen temporaeren Tunnel erreichbar sein, sondern dauerhaft unter einer stabilen URL laufen.

## Empfehlung

Fuer den aktuellen Stand ist `Railway` der pragmatischste erste Produktionspfad.

Gruende:

- Railway kann laut offizieller Doku direkt aus einem `Dockerfile` deployen.
- Der `CMD` aus dem Dockerfile wird als Startkommando verwendet.
- Deployments koennen direkt per CLI oder spaeter automatisiert ueber GitHub laufen.

Offizielle Quellen:

- Railway Deploying with CLI: https://docs.railway.com/cli/deploying
- Railway Dockerfiles: https://docs.railway.com/deploy/dockerfiles
- Railway Build and Start Commands: https://docs.railway.com/reference/build-and-start-commands
- Render Web Services: https://render.com/docs/web-services
- Render Health Checks: https://render.com/docs/health-checks

## Was bereits vorbereitet ist

- `Dockerfile`
- `.dockerignore`
- `railway.toml`
- `render.yaml`
- `GET /health` als Healthcheck-Endpunkt

## Was du mir geben musst

### Fuer Railway

- Zugang zum Railway-Projekt oder die Erlaubnis, dass du die Schritte selbst im Dashboard ausfuehrst
- falls wir GitHub-Deployments wollen: ein GitHub-Repo fuer dieses Projekt

### Fuer Render

- Zugang zum Render-Account oder die Erlaubnis, dass du die Schritte selbst im Dashboard ausfuehrst
- in der Regel ebenfalls ein GitHub-Repo oder ein Docker-Image

### In jedem Fall

- final gewuenschte Produktions-Domain oder Subdomain, falls vorhanden
- Entscheidung fuer die Plattform: `Railway` oder `Render`

## Benoetigte Umgebungsvariablen

Mindestens:

- `OPENAI_API_KEY`
- `API_ALLOWED_ORIGINS`

Optional nur, wenn spaeter auch Pipeline-Jobs auf dem Host laufen sollen:

- `YOUTUBE_API_KEY`
- `YOUTUBE_CHANNEL_ID`
- `TRANSCRIPTLOL_API_KEY`
- `TRANSCRIPTLOL_WORKSPACE_ID`
- `TRANSCRIPTLOL_LANGUAGE`
- `TRANSCRIPTLOL_POLL_SECONDS`
- `TRANSCRIPTLOL_TIMEOUT_SECONDS`

## Wichtiger Architekturhinweis

Fuer den produktiven API-Betrieb braucht die laufende App aktuell nur:

- `reference_library.json`
- `embedding_index.json`
- die Analysebasisdateien, falls lokal ein Rebuild noetig ist

Die eigentliche schwere Pipeline fuer YouTube-/Transcript-Verarbeitung sollte spaeter getrennt vom Live-API-Betrieb laufen.

## Empfohlene Reihenfolge

1. Plattform festlegen: Railway oder Render
2. Projekt in ein GitHub-Repo legen
3. Plattform mit Repo verbinden oder per Railway CLI deployen
4. Environment Variables setzen
5. Healthcheck pruefen
6. Lovable von Tunnel-URL auf feste Produktions-URL umstellen
