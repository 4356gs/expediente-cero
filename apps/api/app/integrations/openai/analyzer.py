"""Official OpenAI Responses API adapter for bounded structured intake analysis."""

import json

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.application.ports import (
    AnalyzedContradiction,
    AnalyzedFact,
    AnalyzedQuestion,
    AnalyzerErrorCode,
    AnalyzerRefusal,
    AnalyzerResult,
    AnalyzerSuccess,
    IntakeAnalyzerError,
    StructuredIntake,
)
from app.domain import Case, DocumentMetadata, SourceMessage
from app.integrations.openai.prompt import (
    INTAKE_ANALYSIS_INSTRUCTIONS,
    INTAKE_ANALYSIS_PROMPT_VERSION,
)
from app.integrations.openai.schemas import IntakeAnalysisOutput


class OpenAIIntakeAnalyzer:
    """Translate the provider response into the application-owned analyzer contract."""

    def __init__(self, client: OpenAI, *, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return INTAKE_ANALYSIS_PROMPT_VERSION

    def analyze(
        self,
        case: Case,
        source_messages: tuple[SourceMessage, ...],
        documents: tuple[DocumentMetadata, ...],
    ) -> AnalyzerResult:
        payload = {
            "case": {
                "procedure_type_selected_by_reviewer": case.procedure_type.value,
                "requested_output_language": case.output_language.value,
            },
            "source_messages": [
                {"source_reference": f"message:{message.id}", "content": message.content}
                for message in source_messages
            ],
            "document_metadata": [
                {
                    "source_reference": f"document:{document.id}",
                    "document_type": document.document_type,
                    "display_name": document.display_name,
                }
                for document in documents
            ],
        }
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=INTAKE_ANALYSIS_INSTRUCTIONS,
                input=json.dumps(payload, ensure_ascii=False),
                text_format=IntakeAnalysisOutput,
                store=False,
            )
        except APITimeoutError as error:
            raise IntakeAnalyzerError(AnalyzerErrorCode.TIMEOUT) from error
        except RateLimitError as error:
            raise IntakeAnalyzerError(
                AnalyzerErrorCode.RATE_LIMIT, request_id=error.request_id
            ) from error
        except APIConnectionError as error:
            raise IntakeAnalyzerError(AnalyzerErrorCode.CONNECTION) from error
        except APIStatusError as error:
            raise IntakeAnalyzerError(
                AnalyzerErrorCode.PROVIDER, request_id=error.request_id
            ) from error
        except Exception as error:
            raise IntakeAnalyzerError(AnalyzerErrorCode.PROVIDER) from error

        request_id = response._request_id
        for item in response.output:
            if item.type == "message" and any(
                content.type == "refusal" for content in item.content
            ):
                return AnalyzerRefusal(request_id=request_id)

        parsed = response.output_parsed
        if parsed is None:
            raise IntakeAnalyzerError(
                AnalyzerErrorCode.NO_STRUCTURED_OUTPUT,
                request_id=request_id,
            )
        return AnalyzerSuccess(
            output=StructuredIntake(
                procedure_type=parsed.procedure_type,
                procedure_reason=parsed.procedure_reason,
                facts=tuple(
                    AnalyzedFact(
                        field=fact.field,
                        value=fact.value,
                        source_reference=fact.source_reference,
                        status=fact.status,
                    )
                    for fact in parsed.facts
                ),
                assumptions=tuple(parsed.assumptions),
                unresolved_questions=tuple(
                    AnalyzedQuestion(
                        code=question.code,
                        question=question.question,
                        reason=question.reason,
                        blocking=question.blocking,
                    )
                    for question in parsed.unresolved_questions
                ),
                contradictions=tuple(
                    AnalyzedContradiction(
                        code=contradiction.code,
                        description=contradiction.description,
                        source_references=tuple(contradiction.source_references),
                        blocking=contradiction.blocking,
                    )
                    for contradiction in parsed.contradictions
                ),
                requested_output_language=parsed.requested_output_language,
            ),
            request_id=request_id,
        )
