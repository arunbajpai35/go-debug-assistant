"""add analyses.prompt_version column

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06 12:30:00
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "alter table analyses add column if not exists prompt_version text not null default 'v1'"
    )
    op.execute(
        "create index if not exists analyses_prompt_version_idx on analyses (prompt_version)"
    )


def downgrade() -> None:
    op.execute("drop index if exists analyses_prompt_version_idx")
    op.execute("alter table analyses drop column if exists prompt_version")
