"""Stable domain vocabulary for Expediente Cero."""

from enum import StrEnum


class ProcedureType(StrEnum):
    """Administrative procedures supported by the MVP."""

    SELF_EMPLOYED_REGISTRATION = "self_employed_registration"
    EMPLOYEE_HIRING = "employee_hiring"
    GRANT_APPLICATION = "grant_application"


class OutputLanguage(StrEnum):
    """Languages supported for reviewer-facing output."""

    SPANISH = "es"
    GALICIAN = "gl"


class CaseStatus(StrEnum):
    """Lifecycle states of a case."""

    DRAFT = "draft"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ANALYSIS_FAILED = "analysis_failed"


class FindingSeverity(StrEnum):
    """Impact of a deterministic validation finding."""

    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class ActorType(StrEnum):
    """Origin of an auditable action."""

    USER = "user"
    SYSTEM = "system"
    MODEL = "model"


class FactStatus(StrEnum):
    """Evidence status of an extracted fact."""

    STATED = "stated"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class ChecklistStatus(StrEnum):
    """Deterministically calculated checklist state."""

    PRESENT = "present"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    NEEDS_REVIEW = "needs_review"


class ReviewDecisionType(StrEnum):
    """Terminal decisions available to a human reviewer."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ModelRunPurpose(StrEnum):
    """Bounded model operations planned for the MVP."""

    INTAKE_ANALYSIS = "intake_analysis"
    FOLLOW_UP_DRAFT = "follow_up_draft"


class ModelRunStatus(StrEnum):
    """Recorded outcome of a bounded model operation."""

    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUSED = "refused"


class AuditEventType(StrEnum):
    """Domain events material to the audit trail."""

    CASE_STATUS_CHANGED = "case_status_changed"
    FOLLOW_UP_GENERATION_STARTED = "follow_up_generation_started"
    FOLLOW_UP_DRAFT_CREATED = "follow_up_draft_created"
    FOLLOW_UP_GENERATION_FAILED = "follow_up_generation_failed"
    FOLLOW_UP_GENERATION_REFUSED = "follow_up_generation_refused"
    FOLLOW_UP_DRAFT_EDITED = "follow_up_draft_edited"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"
