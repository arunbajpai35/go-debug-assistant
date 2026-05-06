"""add parsed structured fields to analyses

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-06 13:30:00
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table analyses add column if not exists category text")
    op.execute("alter table analyses add column if not exists root_cause text")
    op.execute("alter table analyses add column if not exists next_step text")
    op.execute("alter table analyses add column if not exists evidence jsonb")
    op.execute("alter table analyses add column if not exists confidence text")
    op.execute("create index if not exists analyses_category_idx on analyses (category)")
    op.execute("create index if not exists analyses_confidence_idx on analyses (confidence)")


def downgrade() -> None:
    op.execute("drop index if exists analyses_confidence_idx")
    op.execute("drop index if exists analyses_category_idx")
    op.execute("alter table analyses drop column if exists confidence")
    op.execute("alter table analyses drop column if exists evidence")
    op.execute("alter table analyses drop column if exists next_step")
    op.execute("alter table analyses drop column if exists root_cause")
    op.execute("alter table analyses drop column if exists category")
