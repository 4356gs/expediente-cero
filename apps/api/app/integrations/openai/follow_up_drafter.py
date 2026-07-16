"""Responses API adapter for bounded follow-up drafting."""

import json

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.application.ports import (
    DrafterErrorCode,
    DraftingRefusal,
    DraftingResult,
    DraftingSuccess,
    FollowUpDrafterError,
)
from app.domain import (
    Case,
    ChecklistResult,
    DocumentMetadata,
    IntakeAnalysis,
    SourceMessage,
    ValidationFinding,
)
from app.integrations.openai.follow_up_prompt import (
    FOLLOW_UP_DRAFT_INSTRUCTIONS,
    FOLLOW_UP_DRAFT_PROMPT_VERSION,
)
from app.integrations.openai.follow_up_schemas import FollowUpDraftOutput


class OpenAIFollowUpDrafter:
    def __init__(self, client: OpenAI, *, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return FOLLOW_UP_DRAFT_PROMPT_VERSION

    def draft(
        self,
        case: Case,
        source_messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
        analysis: IntakeAnalysis,
        checklist: tuple[ChecklistResult, ...],
        findings: tuple[ValidationFinding, ...],
    ) -> DraftingResult:
        payload = {
            "case": {
                "id": str(case.id),
                "procedure_type": case.procedure_type.value,
                "output_language": case.output_language.value,
            },
            "source_messages": [
                {"id": str(item.id), "content": item.content} for item in source_messages
            ],
            "document_metadata": [
                {
                    "id": str(item.id),
                    "document_type": item.document_type,
                    "display_name": item.display_name,
                }
                for item in documents
            ],
            "analysis": {
                "procedure_type": analysis.procedure_type.value,
                "facts": [
                    {
                        "field": fact.field,
                        "value": fact.value,
                        "status": fact.status.value,
                        "source_reference": fact.source_reference,
                    }
                    for fact in analysis.facts
                ],
                "assumptions": list(analysis.assumptions),
                "unresolved_questions": [
                    {"question": item.question, "reason": item.reason, "blocking": item.blocking}
                    for item in analysis.unresolved_questions
                ],
                "contradictions": [
                    {"description": item.description, "blocking": item.blocking}
                    for item in analysis.contradictions
                ],
            },
            "checklist": [
                {"item_code": item.item_code, "status": item.status.value} for item in checklist
            ],
            "findings": [
                {"code": item.code, "severity": item.severity.value, "message": item.message}
                for item in findings
            ],
        }
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=FOLLOW_UP_DRAFT_INSTRUCTIONS,
                input=json.dumps(payload, ensure_ascii=False),
                text_format=FollowUpDraftOutput,
                store=False,
                max_output_tokens=1200,
            )
        except APITimeoutError as error:
            raise FollowUpDrafterError(DrafterErrorCode.TIMEOUT) from error
        except (APIConnectionError, APIStatusError, RateLimitError) as error:
            raise FollowUpDrafterError(
                DrafterErrorCode.PROVIDER,
                request_id=getattr(error, "request_id", None),
            ) from error
        except Exception as error:
            raise FollowUpDrafterError(DrafterErrorCode.PROVIDER) from error

        request_id = response._request_id
        for item in response.output:
            if item.type == "message" and any(
                content.type == "refusal" for content in item.content
            ):
                return DraftingRefusal(request_id=request_id)
        parsed = response.output_parsed
        text = parsed.text.strip() if parsed is not None else ""
        if not text or len(text) > 4_000:
            raise FollowUpDrafterError(DrafterErrorCode.NO_STRUCTURED_OUTPUT, request_id=request_id)
        return DraftingSuccess(text=text, request_id=request_id)
