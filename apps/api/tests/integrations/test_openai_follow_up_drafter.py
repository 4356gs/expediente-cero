"""Offline contract tests for follow-up Responses API drafting."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from app.application.ports import (
    DrafterErrorCode,
    DraftingRefusal,
    DraftingSuccess,
    FollowUpDrafterError,
)
from app.domain import OutputLanguage, ProcedureType
from app.infrastructure.persistence.fixtures import SYNTHETIC_CASE_FIXTURES
from app.integrations.openai.follow_up_drafter import OpenAIFollowUpDrafter
from app.integrations.openai.follow_up_prompt import FOLLOW_UP_DRAFT_PROMPT_VERSION
from app.integrations.openai.follow_up_schemas import FollowUpDraftOutput
from openai import APIConnectionError, APITimeoutError


def context() -> tuple[object, ...]:
    fixture = SYNTHETIC_CASE_FIXTURES[0]
    analysis = SimpleNamespace(
        procedure_type=ProcedureType.SELF_EMPLOYED_REGISTRATION,
        facts=(),
        assumptions=(),
        unresolved_questions=(),
        contradictions=(),
    )
    return fixture.case, fixture.source_messages, fixture.documents, analysis, (), ()


def test_follow_up_uses_strict_stateless_persisted_payload() -> None:
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        _request_id="req-draft",
        output=[SimpleNamespace(type="message", content=[])],
        output_parsed=FollowUpDraftOutput(text=" Mensaxe persistida "),
    )
    drafter = OpenAIFollowUpDrafter(client, model="gpt-configured")

    result = drafter.draft(*context())  # type: ignore[arg-type]

    assert result == DraftingSuccess(text="Mensaxe persistida", request_id="req-draft")
    assert drafter.model == "gpt-configured"
    assert drafter.prompt_version == FOLLOW_UP_DRAFT_PROMPT_VERSION
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["text_format"] is FollowUpDraftOutput
    assert kwargs["store"] is False
    assert kwargs["max_output_tokens"] == 1200
    assert "tools" not in kwargs
    payload = json.loads(kwargs["input"])
    assert payload["case"]["output_language"] == OutputLanguage.SPANISH.value
    assert payload["source_messages"][0]["content"] == context()[1][0].content


def test_follow_up_refusal_and_empty_output_are_typed() -> None:
    client = Mock()
    drafter = OpenAIFollowUpDrafter(client, model="gpt-5.6")
    client.responses.parse.return_value = SimpleNamespace(
        _request_id="req-refused",
        output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal")])],
        output_parsed=None,
    )
    assert drafter.draft(*context()) == DraftingRefusal(request_id="req-refused")  # type: ignore[arg-type]

    client.responses.parse.return_value = SimpleNamespace(
        _request_id="req-empty", output=[], output_parsed=FollowUpDraftOutput(text=" ")
    )
    with pytest.raises(FollowUpDrafterError) as captured:
        drafter.draft(*context())  # type: ignore[arg-type]
    assert captured.value.code is DrafterErrorCode.NO_STRUCTURED_OUTPUT

    client.responses.parse.return_value = SimpleNamespace(
        _request_id="req-long",
        output=[],
        output_parsed=FollowUpDraftOutput(text="x" * 4_001),
    )
    with pytest.raises(FollowUpDrafterError) as captured:
        drafter.draft(*context())  # type: ignore[arg-type]
    assert captured.value.code is DrafterErrorCode.NO_STRUCTURED_OUTPUT


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (
            APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")),
            DrafterErrorCode.TIMEOUT,
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
            DrafterErrorCode.PROVIDER,
        ),
        (RuntimeError("secret"), DrafterErrorCode.PROVIDER),
    ],
)
def test_follow_up_provider_errors_are_sanitized(
    failure: Exception, code: DrafterErrorCode
) -> None:
    client = Mock()
    client.responses.parse.side_effect = failure
    drafter = OpenAIFollowUpDrafter(client, model="gpt-5.6")
    with pytest.raises(FollowUpDrafterError) as captured:
        drafter.draft(*context())  # type: ignore[arg-type]
    assert captured.value.code is code
    assert "secret" not in str(captured.value)


@pytest.mark.parametrize("procedure", list(ProcedureType))
@pytest.mark.parametrize("language", list(OutputLanguage))
def test_openai_payload_covers_every_procedure_and_language(
    procedure: ProcedureType, language: OutputLanguage
) -> None:
    values = list(context())
    values[0] = replace(values[0], procedure_type=procedure, output_language=language)
    values[3] = SimpleNamespace(
        procedure_type=procedure,
        facts=values[3].facts,
        assumptions=values[3].assumptions,
        unresolved_questions=values[3].unresolved_questions,
        contradictions=values[3].contradictions,
    )
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        _request_id="req-matrix",
        output=[],
        output_parsed=FollowUpDraftOutput(text="Borrador"),
    )
    result = OpenAIFollowUpDrafter(client, model="gpt-5.6").draft(  # type: ignore[arg-type]
        *values
    )
    payload = json.loads(client.responses.parse.call_args.kwargs["input"])
    assert isinstance(result, DraftingSuccess)
    assert payload["case"]["procedure_type"] == procedure.value
    assert payload["case"]["output_language"] == language.value
    assert payload["analysis"]["procedure_type"] == procedure.value
    assert payload["source_messages"][0]["content"] == values[1][0].content
    assert payload["document_metadata"][0]["display_name"] == values[2][0].display_name
