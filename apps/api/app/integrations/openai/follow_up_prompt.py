"""Versioned bounded prompt for follow-up drafting."""

FOLLOW_UP_DRAFT_PROMPT_VERSION = "follow-up-draft-v1"

FOLLOW_UP_DRAFT_INSTRUCTIONS = """You draft one concise follow-up intake message.
Use only the supplied persisted synthetic case data. Write in the requested language.
Ask for missing or contradictory information without giving legal, tax, employment,
accounting, grant, or eligibility advice. Do not add external knowledge.
"""
