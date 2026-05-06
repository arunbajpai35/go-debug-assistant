"""initial schema: raw_logs + analyses

Revision ID: 0001
Revises:
Create Date: 2026-05-06 12:00:00
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists raw_logs (
            id          bigserial primary key,
            trace_id    text        not null,
            level       text        not null,
            message     text        not null,
            ts          timestamptz not null,
            payload     jsonb,
            received_at timestamptz not null default now()
        )
        """
    )
    op.execute("create index if not exists raw_logs_trace_id_idx on raw_logs (trace_id)")
    op.execute("create index if not exists raw_logs_ts_idx on raw_logs (ts)")

    op.execute(
        """
        create table if not exists analyses (
            id         bigserial primary key,
            trace_id   text        not null,
            log_text   text        not null,
            analysis   text        not null,
            model      text        not null,
            created_at timestamptz not null default now()
        )
        """
    )
    op.execute("create index if not exists analyses_trace_id_idx on analyses (trace_id)")
    op.execute("create index if not exists analyses_created_at_idx on analyses (created_at desc)")


def downgrade() -> None:
    op.execute("drop table if exists analyses")
    op.execute("drop table if exists raw_logs")
