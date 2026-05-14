import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
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
        return {
            "status": "ok",
            "database_configured": api_service.database_client.is_configured(),
            "reference_library_exists": paths.reference_library_path.exists(),
            "embedding_index_exists": paths.embedding_index_path.exists(),
            "openai_configured": bool(config.openai_api_key),
        }

    @app.get("/config/options")
    def options():
        return api_service.get_options()

    @app.get("/references")
    def list_references(
        platform: Optional[str] = None,
        format_label: Optional[str] = None,
        hook_label: Optional[str] = None,
        q: str = "",
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ):
        try:
            return api_service.list_references(
                platform=platform,
                format_label=format_label,
                hook_label=hook_label,
                q=q,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/references/{reference_id}")
    def get_reference(reference_id: str):
        try:
            reference = api_service.get_reference(reference_id)
            if reference is None:
                raise HTTPException(status_code=404, detail="Reference not found")
            return reference
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # TODO: PATCH /references/{id}
    # TODO: DELETE /references/{id}

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
                "saved_to": str(output_path.resolve()) if output_path else None,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
