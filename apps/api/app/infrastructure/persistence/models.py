"""SQLAlchemy persistence models kept separate from domain entities."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative metadata root used by Alembic."""


class CaseModel(Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    procedure_type: Mapped[str] = mapped_column(String(48), nullable=False)
    output_language: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    intake_analysis_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    validation_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    validation_template_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    validation_findings: Mapped[list["ValidationFindingModel"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    review_decision: Mapped["ReviewDecisionModel | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", lazy="selectin", uselist=False
    )


class SourceMessageModel(Base):
    __tablename__ = "source_messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentMetadataModel(Base):
    __tablename__ = "document_metadata"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelRunModel(Base):
    __tablename__ = "model_runs"
    __table_args__ = (
        CheckConstraint(
            "(status = 'in_progress' AND completed_at IS NULL) OR "
            "(status IN ('succeeded', 'failed', 'refused') AND completed_at IS NOT NULL)",
            name="ck_model_runs_completion_by_status",
        ),
        Index(
            "uq_model_runs_active_follow_up_case",
            "case_id",
            unique=True,
            sqlite_where=text("purpose = 'follow_up_draft' AND status = 'in_progress'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sanitized_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)


class IntakeAnalysisModel(Base):
    __tablename__ = "intake_analyses"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    procedure_type: Mapped[str] = mapped_column(String(48), nullable=False)
    procedure_reason: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    unresolved_questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    contradictions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requested_output_language: Mapped[str] = mapped_column(String(2), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_runs.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChecklistResultModel(Base):
    __tablename__ = "checklist_results"
    __table_args__ = (Index("ix_checklist_case_item", "case_id", "item_code", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    item_code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ValidationFindingModel(Base):
    __tablename__ = "validation_findings"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    field_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case: Mapped[CaseModel] = relationship(back_populates="validation_findings")


class FollowUpDraftModel(Base):
    __tablename__ = "follow_up_drafts"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_follow_up_drafts_version_positive"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    model_text: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_text: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_runs.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewDecisionModel(Base):
    __tablename__ = "review_decisions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_label: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case: Mapped[CaseModel] = relationship(back_populates="review_decision")


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_case_recorded", "case_id", "recorded_at", "id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_label: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sanitized_metadata: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
