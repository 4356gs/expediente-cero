"""Offline contract tests for the official Responses API adapter."""

from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from app.application.ports import (
    AnalyzerErrorCode,
    AnalyzerRefusal,
    AnalyzerSuccess,
    IntakeAnalyzerError,
)
from app.domain import FactStatus, OutputLanguage, ProcedureType
from app.infrastructure.persistence.fixtures import SYNTHETIC_CASE_FIXTURES
from app.integrations.openai.analyzer import OpenAIIntakeAnalyzer
from app.integrations.openai.prompt import INTAKE_ANALYSIS_PROMPT_VERSION
from app.integrations.openai.schemas import (
    ExtractedFactOutput,
    IntakeAnalysisOutput,
)
from openai import APIConnectionError, APITimeoutError, RateLimitError


def parsed_output() -> IntakeAnalysisOutput:
    return IntakeAnalysisOutput(
        procedure_type=ProcedureType.SELF_EMPLOYED_REGISTRATION,
        procedure_reason="El mensaje solicita preparar un alta sintética.",
        facts=[
            ExtractedFactOutput(
                field="activity",
                value="Diseño sintético",
                source_reference="message:10000000-0000-0000-0000-000000000001",
                status=FactStatus.STATED,
            )
        ],
        assumptions=[],
        unresolved_questions=[],
        contradictions=[],
        requested_output_language=OutputLanguage.SPANISH,
    )


def adapter_with_response(response: object) -> tuple[OpenAIIntakeAnalyzer, Mock]:
    client = Mock()
    client.responses.parse.return_value = response
    return OpenAIIntakeAnalyzer(client, model="gpt-5.6"), client


def test_valid_parsed_response_uses_bounded_stateless_request() -> None:
    response = SimpleNamespace(
        _request_id="req_synthetic",
        output=[SimpleNamespace(type="message", content=[])],
        output_parsed=parsed_output(),
    )
    analyzer, client = adapter_with_response(response)
    fixture = SYNTHETIC_CASE_FIXTURES[0]

    result = analyzer.analyze(fixture.case, fixture.source_messages, fixture.documents)

    assert isinstance(result, AnalyzerSuccess)
    assert result.request_id == "req_synthetic"
    assert result.output.facts[0].status is FactStatus.STATED
    assert INTAKE_ANALYSIS_PROMPT_VERSION == "intake-analysis-v3"
    assert analyzer.prompt_version == INTAKE_ANALYSIS_PROMPT_VERSION
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["model"] == "gpt-5.6"
    assert kwargs["text_format"] is IntakeAnalysisOutput
    assert kwargs["store"] is False
    assert "tools" not in kwargs
    assert "previous_response_id" not in kwargs
    assert "Diseño" not in kwargs["instructions"]
    assert fixture.source_messages[0].content in kwargs["input"]


def test_galician_employee_dates_remain_separate_facts_without_model_contradiction() -> None:
    fixture = SYNTHETIC_CASE_FIXTURES[1]
    source_reference = f"message:{fixture.source_messages[0].id}"
    parsed = IntakeAnalysisOutput(
        procedure_type=ProcedureType.EMPLOYEE_HIRING,
        procedure_reason="A mensaxe solicita unha contratación sintética.",
        facts=[
            ExtractedFactOutput(
                field="employee_name",
                value=None,
                source_reference=None,
                status=FactStatus.UNKNOWN,
            ),
            ExtractedFactOutput(
                field="requested_start_date",
                value="2026-09-01",
                source_reference=source_reference,
                status=FactStatus.STATED,
            ),
            ExtractedFactOutput(
                field="contract_start_date",
                value="2026-09-15",
                source_reference=source_reference,
                status=FactStatus.STATED,
            ),
        ],
        assumptions=[],
        unresolved_questions=[],
        contradictions=[],
        requested_output_language=OutputLanguage.GALICIAN,
    )
    response = SimpleNamespace(
        _request_id="req_galician_employee",
        output=[SimpleNamespace(type="message", content=[])],
        output_parsed=parsed,
    )
    analyzer, client = adapter_with_response(response)

    result = analyzer.analyze(fixture.case, fixture.source_messages, fixture.documents)

    assert isinstance(result, AnalyzerSuccess)
    assert result.output.requested_output_language is OutputLanguage.GALICIAN
    assert [fact.field for fact in result.output.facts[1:]] == [
        "requested_start_date",
        "contract_start_date",
    ]
    assert result.output.contradictions == ()
    instructions = client.responses.parse.call_args.kwargs["instructions"]
    assert "at least two distinct supplied source_reference values" in instructions
    assert "deterministic validation evaluates that date inconsistency later" in instructions


def test_refusal_is_returned_without_retaining_refusal_text() -> None:
    response = SimpleNamespace(
        _request_id="req_refusal",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="refusal", refusal="provider detail")],
            )
        ],
        output_parsed=None,
    )
    analyzer, _client = adapter_with_response(response)
    fixture = SYNTHETIC_CASE_FIXTURES[1]

    result = analyzer.analyze(fixture.case, fixture.source_messages, fixture.documents)

    assert result == AnalyzerRefusal(request_id="req_refusal")


def test_absent_output_parsed_is_a_typed_failure() -> None:
    response = SimpleNamespace(_request_id="req_empty", output=[], output_parsed=None)
    analyzer, _client = adapter_with_response(response)
    fixture = SYNTHETIC_CASE_FIXTURES[2]

    with pytest.raises(IntakeAnalyzerError) as captured:
        analyzer.analyze(fixture.case, fixture.source_messages, fixture.documents)

    assert captured.value.code is AnalyzerErrorCode.NO_STRUCTURED_OUTPUT
    assert captured.value.request_id == "req_empty"


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "request_id"),
    [
        (
            APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")),
            AnalyzerErrorCode.TIMEOUT,
            None,
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
            AnalyzerErrorCode.CONNECTION,
            None,
        ),
        (
            RateLimitError(
                "limited",
                response=httpx.Response(
                    429,
                    headers={"x-request-id": "req_rate"},
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body=None,
            ),
            AnalyzerErrorCode.RATE_LIMIT,
            "req_rate",
        ),
        (RuntimeError("secret provider detail"), AnalyzerErrorCode.PROVIDER, None),
    ],
)
def test_provider_failures_are_sanitized_and_typed(
    provider_error: Exception,
    expected_code: AnalyzerErrorCode,
    request_id: str | None,
) -> None:
    analyzer, client = adapter_with_response(None)
    client.responses.parse.side_effect = provider_error
    fixture = SYNTHETIC_CASE_FIXTURES[0]

    with pytest.raises(IntakeAnalyzerError) as captured:
        analyzer.analyze(fixture.case, fixture.source_messages, fixture.documents)

    assert captured.value.code is expected_code
    assert captured.value.request_id == request_id
    assert "secret provider detail" not in str(captured.value)
