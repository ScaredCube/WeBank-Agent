"""Bounded AI view generation with deterministic and LLM review.

The AI composes values and layout. The server keeps the source digest, rejects
edits to authenticated source facts, and discards a view that cannot pass its
independent reviewer. Result cards are never affected by view failure.
"""
from __future__ import annotations

from typing import Any

from app.agent.llm import LLMProvider
from app.agent.prompt_assembly import assemble_view_review_prompt
from app.agent.ui_composer import get_ui_composer
from app.agent.view_review import ViewReviewError, get_view_reviewer
from app.core.config import settings
from app.schemas.generative_ui import TrustedData, ViewEnvelopeV2, ViewSpec, validate_view_spec
from app.services.view_service import (
    ViewSnapshot, create_ai_view, prepare_ai_view_composition,
    validate_ai_view_data,
)


def _issue_for(exc: Exception) -> list[str]:
    text = str(exc)
    if "可交互" in text or "可交互视图行" in text:
        return ["unstable_id"]
    if "类型" in text:
        return ["invalid_reference"]
    if "来源" in text:
        return ["source_mismatch"]
    return ["invalid_reference"]


async def generate_reviewed_view(
    *, user_id: int, conversation_id: int, question: str,
    results: list[dict[str, Any]], context: ViewSnapshot | None,
    model: LLMProvider,
) -> ViewEnvelopeV2 | None:
    combined, source_data, catalog = prepare_ai_view_composition(context, results)
    if not source_data.metrics and not source_data.datasets:
        return None
    composer = get_ui_composer()
    reviewer = get_view_reviewer(model)
    result_refs = [item["result_ref"] for item in combined]
    issues: list[str] = []
    reviewer_version = assemble_view_review_prompt().version

    for attempt in range(1, settings.view_max_generations + 1):
        try:
            output = await composer.compose(
                question=question, catalog=catalog,
                context=(
                    None if context is None
                    else {
                        "selected_category": (
                            context.envelope.interaction_state.selected_category),
                        "selected_ids": list(
                            context.envelope.interaction_state.selected_ids),
                    }
                ),
                source_data=source_data.model_dump(mode="json"),
                issues=issues,
            )
        except Exception:
            output = None
        if output is None:
            issues = ["invalid_reference"]
            continue

        try:
            parsed_data = TrustedData.model_validate(output["view_data"])
            validate_ai_view_data(parsed_data, source_data)
            validate_view_spec(
                ViewSpec.model_validate(output["spec"]), parsed_data, result_refs,
            )
        except Exception as exc:
            issues = _issue_for(exc)
            continue

        try:
            verdict = await reviewer.review(
                user_request=question,
                source_data=source_data.model_dump(mode="json"),
                view_data=parsed_data.model_dump(mode="json"),
                spec=output["spec"],
            )
        except ViewReviewError:
            # The view is optional; fail closed without a conversational fallback.
            return None
        if verdict.valid:
            return create_ai_view(
                user_id=user_id, conversation_id=conversation_id,
                results=combined, view_data=parsed_data, spec=output["spec"],
                review={
                    "reviewer_version": reviewer_version,
                    "attempts": attempt,
                    "result": "passed",
                },
                context=context,
            )
        issues = list(verdict.issues)
    return None
