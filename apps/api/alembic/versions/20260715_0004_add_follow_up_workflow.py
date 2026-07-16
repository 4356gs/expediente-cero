"""Add follow-up concurrency and model-run lifecycle constraints.

Revision ID: 20260715_0004
Revises: 20260714_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0004"
down_revision: str | None = "20260714_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
    with op.batch_alter_table("audit_events", recreate="always") as batch:
        batch.drop_constraint("ck_audit_events_event_type", type_="check")
        batch.create_check_constraint(
            "ck_audit_events_event_type",
            "event_type IN ('case_status_changed', 'follow_up_generation_started', "
            "'follow_up_draft_created', 'follow_up_generation_failed', "
            "'follow_up_generation_refused', 'follow_up_draft_edited', "
            "'review_approved', 'review_rejected')",
        )
    op.execute(
        "CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"
    )
    with op.batch_alter_table("follow_up_drafts", recreate="always") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.create_check_constraint("ck_follow_up_drafts_version_positive", "version >= 1")

    with op.batch_alter_table("model_runs", recreate="always") as batch:
        batch.create_check_constraint(
            "ck_model_runs_completion_by_status",
            "(status = 'in_progress' AND completed_at IS NULL) OR "
            "(status IN ('succeeded', 'failed', 'refused') AND completed_at IS NOT NULL)",
        )

    op.create_index(
        "uq_model_runs_active_follow_up_case",
        "model_runs",
        ["case_id"],
        unique=True,
        sqlite_where=sa.text("purpose = 'follow_up_draft' AND status = 'in_progress'"),
    )


def downgrade() -> None:
    op.drop_index("uq_model_runs_active_follow_up_case", table_name="model_runs")
    with op.batch_alter_table("model_runs", recreate="always") as batch:
        batch.drop_constraint("ck_model_runs_completion_by_status", type_="check")
    with op.batch_alter_table("follow_up_drafts", recreate="always") as batch:
        batch.drop_constraint("ck_follow_up_drafts_version_positive", type_="check")
        batch.drop_column("version")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
    with op.batch_alter_table("audit_events", recreate="always") as batch:
        batch.drop_constraint("ck_audit_events_event_type", type_="check")
        batch.create_check_constraint(
            "ck_audit_events_event_type", "event_type IN ('case_status_changed')"
        )
    op.execute(
        "CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END"
    )
