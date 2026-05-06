"""partition the analyses table by month on created_at.

approach:
  1. rename existing analyses to analyses_old
  2. create new partitioned analyses (range on created_at) with the same columns + indexes
  3. create a DEFAULT partition (catches any insert outside declared ranges so writes never fail)
  4. create monthly partitions for the project's expected lifetime (2026-05 through 2027-06)
  5. copy data from analyses_old, advance the sequence past max(id), drop the old table

partitioning constraints in postgres 11+:
  - partition key must be part of the primary key, so PK is (id, created_at) — id is still
    practically unique because the bigserial sequence is shared.
  - indexes declared on the parent propagate to all current + future partitions.

new partitions for later months are added via scripts/create_analysis_partitions.py.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-06 14:00:00
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


MONTHS = [
    ("2026-05", "2026-06"),
    ("2026-06", "2026-07"),
    ("2026-07", "2026-08"),
    ("2026-08", "2026-09"),
    ("2026-09", "2026-10"),
    ("2026-10", "2026-11"),
    ("2026-11", "2026-12"),
    ("2026-12", "2027-01"),
    ("2027-01", "2027-02"),
    ("2027-02", "2027-03"),
    ("2027-03", "2027-04"),
    ("2027-04", "2027-05"),
    ("2027-05", "2027-06"),
    ("2027-06", "2027-07"),
]


def upgrade() -> None:
    op.execute("alter table if exists analyses rename to analyses_old")

    op.execute(
        """
        create table analyses (
            id              bigserial,
            trace_id        text        not null,
            log_text        text        not null,
            analysis        text        not null,
            model           text        not null,
            prompt_version  text        not null default 'v1',
            category        text,
            root_cause      text,
            next_step       text,
            evidence        jsonb,
            confidence      text,
            created_at      timestamptz not null default now(),
            primary key (id, created_at)
        ) partition by range (created_at)
        """
    )

    op.execute("create index if not exists analyses_trace_id_idx on analyses (trace_id)")
    op.execute("create index if not exists analyses_created_at_idx on analyses (created_at desc)")
    op.execute("create index if not exists analyses_prompt_version_idx on analyses (prompt_version)")
    op.execute("create index if not exists analyses_category_idx on analyses (category)")
    op.execute("create index if not exists analyses_confidence_idx on analyses (confidence)")

    op.execute("create table if not exists analyses_default partition of analyses default")

    for start, end in MONTHS:
        partition = f"analyses_y{start[:4]}m{start[5:7]}"
        op.execute(
            f"create table if not exists {partition} partition of analyses "
            f"for values from ('{start}-01') to ('{end}-01')"
        )

    op.execute(
        """
        insert into analyses (id, trace_id, log_text, analysis, model, prompt_version,
                              category, root_cause, next_step, evidence, confidence, created_at)
        select id, trace_id, log_text, analysis, model, prompt_version,
               category, root_cause, next_step, evidence, confidence, created_at
        from analyses_old
        """
    )

    op.execute("select setval('analyses_id_seq', coalesce((select max(id) from analyses), 1))")
    op.execute("drop table analyses_old")


def downgrade() -> None:
    op.execute("alter table if exists analyses rename to analyses_partitioned")
    op.execute(
        """
        create table analyses (
            id              bigserial primary key,
            trace_id        text        not null,
            log_text        text        not null,
            analysis        text        not null,
            model           text        not null,
            prompt_version  text        not null default 'v1',
            category        text,
            root_cause      text,
            next_step       text,
            evidence        jsonb,
            confidence      text,
            created_at      timestamptz not null default now()
        )
        """
    )
    op.execute(
        """
        insert into analyses (id, trace_id, log_text, analysis, model, prompt_version,
                              category, root_cause, next_step, evidence, confidence, created_at)
        select id, trace_id, log_text, analysis, model, prompt_version,
               category, root_cause, next_step, evidence, confidence, created_at
        from analyses_partitioned
        """
    )
    op.execute("create index if not exists analyses_trace_id_idx on analyses (trace_id)")
    op.execute("create index if not exists analyses_created_at_idx on analyses (created_at desc)")
    op.execute("create index if not exists analyses_prompt_version_idx on analyses (prompt_version)")
    op.execute("create index if not exists analyses_category_idx on analyses (category)")
    op.execute("create index if not exists analyses_confidence_idx on analyses (confidence)")
    op.execute("drop table analyses_partitioned")
