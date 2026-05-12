import argparse
import json
import re
from pathlib import Path
from datetime import datetime

from youtube_ki_bot.embedding_service import EmbeddingService
from youtube_ki_bot.generation_service import ScriptGenerationService
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


def retrieve_references(config, paths, args):
    references = load_reference_library(paths)
    embedding_index = None
    if paths.embedding_index_path.exists():
        embedding_index = json.loads(paths.embedding_index_path.read_text(encoding="utf-8"))

    retrieval_service = RetrievalService(
        EmbeddingService(
            api_key=config.openai_api_key,
            model=config.embedding_model,
        )
    )
    results = retrieval_service.retrieve(
        references=references,
        query_text=args.query or "",
        platform=args.platform,
        format_label=args.format_label,
        hook_label=args.hook_label,
        top_k=args.top_k,
        embedding_index=embedding_index,
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

    references = load_reference_library(paths)
    embedding_index = None
    if paths.embedding_index_path.exists():
        embedding_index = json.loads(paths.embedding_index_path.read_text(encoding="utf-8"))

    retrieval_service = RetrievalService(
        EmbeddingService(
            api_key=config.openai_api_key,
            model=config.embedding_model,
        )
    )
    results = retrieval_service.retrieve(
        references=references,
        query_text=args.brief,
        platform=args.platform,
        format_label=args.format_label,
        hook_label=args.hook_label,
        top_k=args.top_k,
        embedding_index=embedding_index,
    )

    generator = ScriptGenerationService(
        api_key=config.openai_api_key,
        model=config.generation_model,
    )
    output = generator.generate_script(
        brief=args.brief,
        retrieval_results=results,
        platform=args.platform,
        format_label=args.format_label,
        hook_label=args.hook_label,
    )
    payload = extract_json_payload(output)
    output_path = save_generated_script(paths, args.brief, payload, results)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nScript gespeichert unter: {output_path.resolve()}")


def build_parser():
    parser = argparse.ArgumentParser(description="YouTube Shorts KI Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("pipeline", help="Vollständige Analyse-Pipeline ausführen")
    subparsers.add_parser("build-library", help="Referenzbibliothek aus Analyse-Dateien bauen")
    subparsers.add_parser("build-embeddings", help="OpenAI Embeddings für Referenzbibliothek bauen")

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
    require_youtube = command == "pipeline"
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
    if command == "retrieve":
        retrieve_references(config, paths, args)
        return
    if command == "generate-script":
        generate_script(config, paths, args)
        return

    parser.error(f"Unbekannter Befehl: {command}")


if __name__ == "__main__":
    main()
