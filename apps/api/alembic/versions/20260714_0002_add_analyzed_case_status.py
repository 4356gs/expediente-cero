"""Add the analyzed case lifecycle state.

Revision ID: 20260714_0002
Revises: 20260713_0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260714_0002"
down_revision: str | None = "20260713_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_status_constraint(*, include_analyzed: bool) -> None:
    statuses = ["draft", "analyzing"]
    if include_analyzed:
        statuses.append("analyzed")
    statuses.extend(["needs_review", "approved", "rejected", "analysis_failed"])
    allowed = ", ".join(f"'{status}'" for status in statuses)
    with op.batch_alter_table("cases", recreate="always") as batch:
        batch.drop_constraint("ck_cases_status", type_="check")
        if not include_analyzed:
            batch.drop_constraint("ck_cases_analyzed_requires_analysis", type_="check")
        batch.create_check_constraint("ck_cases_status", f"status IN ({allowed})")
        if include_analyzed:
            batch.create_check_constraint(
                "ck_cases_analyzed_requires_analysis",
                "status != 'analyzed' OR intake_analysis_id IS NOT NULL",
            )


def upgrade() -> None:
    _replace_status_constraint(include_analyzed=True)


def downgrade() -> None:
    # The previous revision cannot represent a completed, unvalidated analysis.
    # Preserve its records while moving the case to the only safe non-review state.
    op.execute("UPDATE cases SET status = 'analysis_failed' WHERE status = 'analyzed'")
    _replace_status_constraint(include_analyzed=False)
