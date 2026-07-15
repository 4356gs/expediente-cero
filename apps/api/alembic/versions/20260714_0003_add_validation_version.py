"""Add deterministic validation version and review-ready persistence guard.

Revision ID: 20260714_0003
Revises: 20260714_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0003"
down_revision: str | None = "20260714_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cases", recreate="always") as batch:
        batch.add_column(sa.Column("validation_template_version", sa.String(64), nullable=True))
        batch.create_check_constraint(
            "ck_cases_validation_pair",
            "(validation_completed_at IS NULL AND validation_template_version IS NULL) OR "
            "(validation_completed_at IS NOT NULL AND validation_template_version IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_cases_review_requires_validation",
            "status NOT IN ('needs_review', 'approved', 'rejected') OR "
            "(validation_completed_at IS NOT NULL AND validation_template_version IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("cases", recreate="always") as batch:
        batch.drop_constraint("ck_cases_review_requires_validation", type_="check")
        batch.drop_constraint("ck_cases_validation_pair", type_="check")
        batch.drop_column("validation_template_version")
