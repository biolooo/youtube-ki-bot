import json

from youtube_ki_bot.database import DatabaseClient


class DatabaseGenerationRepository:
    def __init__(self, database_client: DatabaseClient):
        self.database_client = database_client

    def is_configured(self) -> bool:
        return self.database_client.is_configured()

    def persist_generation(
        self,
        request,
        retrieval_request: dict,
        retrieval_results: list,
        payload: dict,
        model: str,
    ) -> dict:
        if not self.is_configured():
            raise ValueError("DATABASE_URL fehlt.")

        request_id = None
        generated_script_id = None
        with self.database_client.connection() as connection:
            with connection.cursor() as cursor:
                request_id = self._insert_generation_request(
                    cursor,
                    request=request,
                    retrieval_query=retrieval_request.get("query_text", ""),
                )
                generated_script_id = self._insert_generated_script(
                    cursor,
                    request_id=request_id,
                    payload=payload,
                    model=model,
                )
                self._insert_script_reference_links(
                    cursor,
                    generated_script_id=generated_script_id,
                    retrieval_results=retrieval_results,
                )
            connection.commit()

        return {
            "request_id": str(request_id),
            "generated_script_id": str(generated_script_id),
        }

    @staticmethod
    def _insert_generation_request(cursor, request, retrieval_query: str):
        sql = """
        insert into generation_requests (
            topic,
            database_id,
            platform,
            format_label,
            hook_label,
            goal,
            tone,
            target_length_seconds,
            constraints,
            freeform_brief,
            retrieval_query,
            top_k,
            request_payload
        ) values (
            %(topic)s,
            %(database_id)s,
            %(platform)s,
            %(format_label)s,
            %(hook_label)s,
            %(goal)s,
            %(tone)s,
            %(target_length_seconds)s,
            %(constraints)s,
            %(freeform_brief)s,
            %(retrieval_query)s,
            %(top_k)s,
            %(request_payload)s::jsonb
        )
        returning id
        """
        cursor.execute(
            sql,
            {
                "topic": request.topic,
                "database_id": request.database_id,
                "platform": request.platform,
                "format_label": request.format_label,
                "hook_label": request.hook_label,
                "goal": request.goal,
                "tone": request.tone,
                "target_length_seconds": request.target_length_seconds,
                "constraints": request.constraints,
                "freeform_brief": request.freeform_brief,
                "retrieval_query": retrieval_query,
                "top_k": request.top_k,
                "request_payload": json.dumps(request.to_dict(), ensure_ascii=False),
            },
        )
        row = cursor.fetchone()
        return row[0]

    @staticmethod
    def _insert_generated_script(cursor, request_id, payload: dict, model: str):
        sql = """
        insert into generated_scripts (
            request_id,
            variant_index,
            title_ideas,
            hook,
            script,
            cta,
            why_this_should_work,
            model,
            response_payload
        ) values (
            %(request_id)s,
            %(variant_index)s,
            %(title_ideas)s::jsonb,
            %(hook)s,
            %(script)s,
            %(cta)s,
            %(why_this_should_work)s::jsonb,
            %(model)s,
            %(response_payload)s::jsonb
        )
        returning id
        """
        cursor.execute(
            sql,
            {
                "request_id": request_id,
                "variant_index": 1,
                "title_ideas": json.dumps(payload.get("title_ideas", []), ensure_ascii=False),
                "hook": payload.get("hook", ""),
                "script": payload.get("script", ""),
                "cta": payload.get("cta", ""),
                "why_this_should_work": json.dumps(
                    payload.get("why_this_should_work", []),
                    ensure_ascii=False,
                ),
                "model": model,
                "response_payload": json.dumps(payload, ensure_ascii=False),
            },
        )
        row = cursor.fetchone()
        return row[0]

    @staticmethod
    def _insert_script_reference_links(cursor, generated_script_id, retrieval_results: list):
        sql = """
        insert into script_reference_links (
            generated_script_id,
            video_id,
            retrieval_score,
            metadata_score,
            keyword_score,
            semantic_score,
            performance_score
        ) values (
            %(generated_script_id)s,
            %(video_id)s,
            %(retrieval_score)s,
            %(metadata_score)s,
            %(keyword_score)s,
            %(semantic_score)s,
            %(performance_score)s
        )
        """
        payload = [
            {
                "generated_script_id": generated_script_id,
                "video_id": item["reference"]["video_id"],
                "retrieval_score": item["score"],
                "metadata_score": item["metadata_score"],
                "keyword_score": item["keyword_score"],
                "semantic_score": item["semantic_score"],
                "performance_score": item["performance_score"],
            }
            for item in retrieval_results
        ]
        if payload:
            cursor.executemany(sql, payload)
