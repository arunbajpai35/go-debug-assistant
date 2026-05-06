alter table analyses
    add column if not exists prompt_version text not null default 'v1';

create index if not exists analyses_prompt_version_idx on analyses (prompt_version);
