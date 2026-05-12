import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from youtube_ki_bot.api_service import ApiService
from youtube_ki_bot.app_models import GenerationRequest, RetrievalRequest
from youtube_ki_bot.settings import load_app_config


class RetrievalRequestBody(BaseModel):
    query_text: str = ""
    platform: Optional[str] = None
    format_label: Optional[str] = None
    hook_label: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class GenerationRequestBody(BaseModel):
    topic: str
    platform: Optional[str] = None
    format_label: Optional[str] = None
    hook_label: Optional[str] = None
    goal: Optional[str] = None
    tone: Optional[str] = None
    target_length_seconds: Optional[int] = Field(default=None, ge=5, le=180)
    constraints: Optional[str] = None
    freeform_brief: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


def _allowed_origins() -> list:
    raw = os.getenv("API_ALLOWED_ORIGINS", "*")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["*"]


def create_app() -> FastAPI:
    base_dir = Path(__file__).resolve().parent.parent
    config, paths = load_app_config(base_dir, require_youtube=False)
    api_service = ApiService(config, paths)

    app = FastAPI(
        title="YouTube KI Bot API",
        version="0.1.0",
        description="API fuer Retrieval und Script-Generierung, geeignet fuer Lovable-Frontends.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        openai_key = config.openai_api_key or ""
        return {
            "status": "ok",
            "reference_library_exists": paths.reference_library_path.exists(),
            "embedding_index_exists": paths.embedding_index_path.exists(),
            "openai_configured": bool(openai_key),
            "openai_key_length": len(openai_key),
            "openai_key_prefix": openai_key[:7] if openai_key else "",
        }

    @app.get("/config/options")
    def options():
        return {
            "platform_examples": [
                "nintendo_3ds",
                "nintendo_wii",
                "nintendo_switch",
                "playstation_psp",
                "playstation_ps3",
                "playstation_ps2",
            ],
            "format_examples": [
                "tutorial_guide",
                "technical_modding",
                "order_packaging",
                "buying_advice",
                "retro_nostalgia",
                "opinion_hot_take",
            ],
            "hook_examples": [
                "question_hook",
                "controversy_hook",
                "problem_solution",
                "direct_address",
                "customer_story",
            ],
        }

    @app.post("/retrieve-references")
    def retrieve_references(body: RetrievalRequestBody):
        try:
            request = RetrievalRequest(
                query_text=body.query_text,
                platform=body.platform,
                format_label=body.format_label,
                hook_label=body.hook_label,
                top_k=body.top_k,
            )
            results = api_service.retrieve_references(request)
            return {
                "count": len(results),
                "results": results,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/generate-script")
    def generate_script(body: GenerationRequestBody):
        try:
            request = GenerationRequest(
                topic=body.topic,
                platform=body.platform,
                format_label=body.format_label,
                hook_label=body.hook_label,
                goal=body.goal,
                tone=body.tone,
                target_length_seconds=body.target_length_seconds,
                constraints=body.constraints,
                freeform_brief=body.freeform_brief,
                top_k=body.top_k,
            )
            payload, retrieval_results, output_path = api_service.generate_script(request)
            return {
                "request": request.to_dict(),
                "script_payload": payload,
                "references_used": retrieval_results,
                "saved_to": str(output_path.resolve()),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
