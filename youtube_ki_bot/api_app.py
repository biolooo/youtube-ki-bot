import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from youtube_ki_bot.api_service import ApiService
from youtube_ki_bot.app_models import GenerationRequest, RetrievalRequest
from youtube_ki_bot.settings import load_app_config


class RetrievalRequestBody(BaseModel):
    query_text: str = ""
    database_id: Optional[str] = None
    platform: Optional[str] = None
    format_label: Optional[str] = None
    hook_label: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class GenerationRequestBody(BaseModel):
    topic: str
    database_id: Optional[str] = None
    platform: Optional[str] = None
    format_label: Optional[str] = None
    hook_label: Optional[str] = None
    goal: Optional[str] = None
    tone: Optional[str] = None
    target_length_seconds: Optional[int] = Field(default=None, ge=5, le=180)
    constraints: Optional[str] = None
    freeform_brief: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class DatabaseCreateBody(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class TableInsertBody(BaseModel):
    data: dict


class TableUpdateBody(BaseModel):
    match: dict
    data: dict


class TableDeleteBody(BaseModel):
    match: dict


def _allowed_origins() -> list:
    raw = os.getenv("API_ALLOWED_ORIGINS", "*")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["*"]


def _error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


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

    @app.get("/databases")
    def list_databases():
        try:
            databases = api_service.list_databases()
            tables = api_service.list_tables()
            return {
                "databases": databases,
                "total": len(databases),
                "tables": tables,
                "table_total": len(tables),
            }
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.get("/tables/{schema}/{name}/rows")
    def get_table_rows(
        schema: str,
        name: str,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        try:
            return api_service.get_table_rows(schema=schema, name=name, limit=limit, offset=offset)
        except LookupError as exc:
            return _error_response(str(exc), 404)
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.post("/tables/{schema}/{name}/rows")
    def create_table_row(schema: str, name: str, body: TableInsertBody):
        try:
            return api_service.insert_table_row(schema=schema, name=name, data=body.data)
        except LookupError as exc:
            return _error_response(str(exc), 404)
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.patch("/tables/{schema}/{name}/rows")
    def update_table_rows(schema: str, name: str, body: TableUpdateBody):
        try:
            return api_service.update_table_rows(
                schema=schema,
                name=name,
                match=body.match,
                data=body.data,
            )
        except LookupError as exc:
            return _error_response(str(exc), 404)
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.delete("/tables/{schema}/{name}/rows")
    def delete_table_rows(schema: str, name: str, body: TableDeleteBody):
        try:
            return api_service.delete_table_rows(schema=schema, name=name, match=body.match)
        except LookupError as exc:
            return _error_response(str(exc), 404)
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.get("/databases/{database_id}")
    def get_database(database_id: str):
        try:
            database = api_service.get_database(database_id)
            if database is None:
                return _error_response("Database not found", 404)
            return database
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.get("/databases/{database_id}/references")
    def list_database_references(database_id: str):
        try:
            if api_service.get_database(database_id) is None:
                return _error_response("Database not found", 404)
            result = api_service.list_references(database_id=database_id, limit=1000, offset=0)
            return result
        except LookupError as exc:
            return _error_response(str(exc), 404)
        except ValueError as exc:
            return _error_response(str(exc), 400)
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.post("/databases")
    def create_database(body: DatabaseCreateBody):
        try:
            database = api_service.create_database(
                database_id=body.id,
                name=body.name,
                description=body.description,
            )
            return database
        except Exception as exc:
            return _error_response(str(exc), 500)

    @app.delete("/databases/{database_id}")
    def delete_database(database_id: str):
        try:
            deleted = api_service.delete_database(database_id)
            if not deleted:
                return _error_response("Database not found", 404)
            return {"deleted": True, "id": database_id}
        except Exception as exc:
            return _error_response(str(exc), 500)

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
                database_id=body.database_id,
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
        except LookupError as exc:
            return _error_response(str(exc), 404)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/generate-script")
    def generate_script(body: GenerationRequestBody):
        try:
            request = GenerationRequest(
                topic=body.topic,
                database_id=body.database_id,
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
        except LookupError as exc:
            return _error_response(str(exc), 404)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
