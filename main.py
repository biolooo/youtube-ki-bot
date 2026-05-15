import argparse
import json
import re
from pathlib import Path
from datetime import datetime

from youtube_ki_bot.api_service import ApiService
from youtube_ki_bot.app_models import GenerationRequest, RetrievalRequest
from youtube_ki_bot.embedding_service import EmbeddingService
from youtube_ki_bot.generation_service import ScriptGenerationService
from youtube_ki_bot.database import DatabaseClient
from youtube_ki_bot.database_importer import DatabaseImporter
from youtube_ki_bot.reference_repository import ReferenceRepository
from youtube_ki_bot.retrieval_service import RetrievalService
from youtube_ki_bot.settings import load_app_config
from youtube_ki_bot.storage import CsvJsonStorage
from youtube_ki_bot.settings import ensure_directory


def build_reference_library(config, paths):
    repository = ReferenceRepository(
        paths.analysis_csv_path,
        paths.top_references_csv_path,
    )
    references = repository.build_reference_library()
    CsvJsonStorage().save_json({"references": references}, paths.reference_library_path)
    print(f"Referenzbibliothek gespeichert unter: {paths.reference_library_path.resolve()}")
    print(f"Referenzvideos insgesamt: {len(references)}")


def load_reference_library(paths):
    if not paths.reference_library_path.exists():
        raise FileNotFoundError(
            f"Referenzbibliothek fehlt: {paths.reference_library_path}. "
            f"Bitte zuerst `build-library` ausführen."
        )
    payload = json.loads(paths.reference_library_path.read_text(encoding="utf-8"))
    return payload.get("references", [])


def slugify_filename(text, max_length=60):
    normalized = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß\s-]", "", text).strip().lower()
    normalized = normalized.replace("ß", "ss")
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized[:max_length] or "script"


def extract_json_payload(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def save_generated_script(paths, brief, payload, retrieval_results):
    ensure_directory(paths.generated_scripts_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify_filename(payload.get("title_ideas", [brief])[0] if payload.get("title_ideas") else brief)
    output_path = paths.generated_scripts_dir / f"{timestamp}_{slug}.json"
    output_payload = {
        "created_at": datetime.now().isoformat(),
        "brief": brief,
        "script_payload": payload,
        "references_used": [
            {
                "score": item["score"],
                "video_id": item["reference"]["video_id"],
                "title": item["reference"]["title"],
                "url": item["reference"]["url"],
                "platform_labels": item["reference"]["platform_labels"],
                "format_labels": item["reference"]["format_labels"],
                "hook_labels": item["reference"]["hook_labels"],
            }
            for item in retrieval_results
        ],
    }
    CsvJsonStorage().save_json(output_payload, output_path)
    return output_path


def build_embedding_index(config, paths):
    references = load_reference_library(paths)
    embedding_service = EmbeddingService(
        api_key=config.openai_api_key,
        model=config.embedding_model,
    )
    if not embedding_service.is_available():
        raise ValueError("OPENAI_API_KEY fehlt. Embeddings können noch nicht gebaut werden.")
    retrieval_service = RetrievalService(embedding_service)
    embedding_index = retrieval_service.build_embedding_index(references)
    CsvJsonStorage().save_json(embedding_index, paths.embedding_index_path)
    print(f"Embedding-Index gespeichert unter: {paths.embedding_index_path.resolve()}")
    print(f"Embedding-Items insgesamt: {len(embedding_index.get('items', []))}")


def database_health(config):
    database_client = DatabaseClient(config.database_url)
    if not database_client.is_configured():
        raise ValueError("DATABASE_URL fehlt.")
    is_reachable = database_client.ping()
    print(f"Datenbank erreichbar: {is_reachable}")


def import_database(config, paths):
    database_client = DatabaseClient(config.database_url)
    importer = DatabaseImporter(database_client, paths)
    result = importer.import_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def backfill_database(config, paths):
    database_client = DatabaseClient(config.database_url)
    importer = DatabaseImporter(database_client, paths)
    result = importer.import_from_reference_library()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def retrieve_references(config, paths, args):
    api_service = ApiService(config, paths)
    results = api_service.retrieve_references(
        RetrievalRequest(
            query_text=args.query or "",
            platform=args.platform,
            format_label=args.format_label,
            hook_label=args.hook_label,
            top_k=args.top_k,
        )
    )
    print(f"Gefundene Referenzen: {len(results)}")
    for index, item in enumerate(results, start=1):
        reference = item["reference"]
        print("-------------------")
        print(f"#{index}: {reference['title']}")
        print(f"Score: {item['score']}")
        print(f"Views: {reference['views']}")
        print(f"Plattformen: {', '.join(reference['platform_labels'])}")
        print(f"Formate: {', '.join(reference['format_labels'])}")
        print(f"Hooks: {', '.join(reference['hook_labels'])}")
        print(f"Hook-Text: {reference['hook_text']}")
        print(f"URL: {reference['url']}")


def generate_script(config, paths, args):
    if not config.openai_api_key:
        raise ValueError("OPENAI_API_KEY fehlt. Script-Generierung ist noch nicht möglich.")

    api_service = ApiService(config, paths)
    payload, results, output_path = api_service.generate_script(
        GenerationRequest(
            topic=args.brief,
            platform=args.platform,
            format_label=args.format_label,
            hook_label=args.hook_label,
            top_k=args.top_k,
        )
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if output_path:
        print(f"\nScript gespeichert unter: {output_path.resolve()}")
    else:
        print("\nScript wurde nicht automatisch gespeichert.")


def sync_channel(config, paths, process_limit=None):
    from youtube_ki_bot.channel_sync_service import ChannelSyncService

    result = ChannelSyncService(config, paths).run(process_limit=process_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description="YouTube Shorts KI Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("pipeline", help="Vollständige Analyse-Pipeline ausführen")
    subparsers.add_parser("build-library", help="Referenzbibliothek aus Analyse-Dateien bauen")
    subparsers.add_parser("build-embeddings", help="OpenAI Embeddings für Referenzbibliothek bauen")
    subparsers.add_parser("db-health", help="Datenbank-Verbindung prüfen")
    subparsers.add_parser("db-import", help="Bestehende Daten nach Postgres/Supabase importieren")
    subparsers.add_parser(
        "db-backfill-references",
        help="DB aus reference_library.json, embedding_index.json und transcripts/ backfillen",
    )
    sync_parser = subparsers.add_parser(
        "sync-channel",
        help="Kanal scannen, alle Kennzahlen aktualisieren und fehlende Shorts verarbeiten",
    )
    sync_parser.add_argument(
        "--limit",
        type=int,
        help="Maximale Anzahl fehlender Shorts, die in diesem Lauf transkribiert werden",
    )

    daily_sync_parser = subparsers.add_parser(
        "daily-sync",
        help="Tageslauf: alle Metriken aktualisieren und standardmäßig max. 5 fehlende Shorts verarbeiten",
    )
    daily_sync_parser.add_argument(
        "--limit",
        type=int,
        help="Optionales Override für den Tageslauf. Standard kommt aus SYNC_MAX_SHORTS_PER_RUN.",
    )

    retrieve_parser = subparsers.add_parser("retrieve", help="Beste Referenzvideos abrufen")
    retrieve_parser.add_argument("--query", default="", help="Freitext-Idee oder Suchquery")
    retrieve_parser.add_argument("--platform", help="Primäre Plattform, z. B. playstation_ps3")
    retrieve_parser.add_argument("--format-label", help="Zielformat, z. B. tutorial_guide")
    retrieve_parser.add_argument("--hook-label", help="Hook-Typ, z. B. controversy_hook")
    retrieve_parser.add_argument("--top-k", type=int, default=5, help="Anzahl Ergebnisse")

    generate_parser = subparsers.add_parser("generate-script", help="Script per OpenAI generieren")
    generate_parser.add_argument("--brief", required=True, help="Briefing für das neue Video")
    generate_parser.add_argument("--platform", help="Primäre Plattform, z. B. playstation_ps3")
    generate_parser.add_argument("--format-label", help="Zielformat, z. B. tutorial_guide")
    generate_parser.add_argument("--hook-label", help="Hook-Typ, z. B. controversy_hook")
    generate_parser.add_argument("--top-k", type=int, default=5, help="Anzahl Referenzen")

    return parser


def main():
    base_dir = Path(__file__).resolve().parent
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "pipeline"
    require_youtube = command in {"pipeline", "sync-channel", "daily-sync"}
    config, paths = load_app_config(base_dir, require_youtube=require_youtube)

    if command == "pipeline":
        from youtube_ki_bot.orchestrator import PipelineOrchestrator
        PipelineOrchestrator(config, paths).run()
        return
    if command == "build-library":
        build_reference_library(config, paths)
        return
    if command == "build-embeddings":
        build_embedding_index(config, paths)
        return
    if command == "db-health":
        database_health(config)
        return
    if command == "db-import":
        import_database(config, paths)
        return
    if command == "db-backfill-references":
        backfill_database(config, paths)
        return
    if command == "sync-channel":
        sync_channel(config, paths, process_limit=args.limit)
        return
    if command == "daily-sync":
        sync_channel(config, paths, process_limit=args.limit)
        return
    if command == "retrieve":
        retrieve_references(config, paths, args)
        return
    if command == "generate-script":
        generate_script(config, paths, args)
        return

    parser.error(f"Unbekannter Befehl: {command}")


if __name__ == "__main__":
    main()
