"""Strict Structured Output schema for a follow-up draft."""

from pydantic import BaseModel, ConfigDict


class FollowUpDraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str
