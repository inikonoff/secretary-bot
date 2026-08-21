-- Secretary bot schema (TZ v1.1 p.59). Idempotent: safe to re-run.

do $$ begin
    create type application_status as enum ('new','viewed','in_progress','completed','rejected');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type revision_status as enum ('new','viewed','in_progress','done');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type application_state as enum (
        'idle','creating','waiting_initial_description','interview',
        'waiting_deadline','understanding','adding_information','waiting_confirmation',
        'finalizing','finalized','cancelled'
    );
exception when duplicate_object then null;
end $$;

create table if not exists users (
    id bigserial primary key,
    telegram_id bigint not null unique,
    username text,
    first_name text,
    language_code text,
    is_blocked boolean not null default false,
    blocked_at timestamptz,
    created_at timestamptz not null default now(),
    last_active_at timestamptz not null default now()
);

create table if not exists applications (
    id bigserial primary key,
    user_id bigint not null references users(id) on delete cascade,
    status application_status not null default 'new',
    state application_state not null default 'creating',
    client_understanding_text text,
    project_context jsonb not null default '{}'::jsonb,
    deadline_text text,
    pending_understanding_message text,
    last_cancel_message_id bigint,
    tz_markdown_path text,
    tz_markdown_content text,
    add_info_count int not null default 0,
    clarifying_questions_count int not null default 0,
    same_topic_retry_count int not null default 0,
    current_question_topic text,
    flagged_as_abuse boolean not null default false,
    reminder_sent_at timestamptz,
    created_at timestamptz not null default now(),
    confirmed_at timestamptz,
    updated_at timestamptz not null default now()
);

-- Mandatory per TZ p.59: hot path for checking an unfinished session on /new.
create index if not exists idx_applications_user_state on applications (user_id, state);
create index if not exists idx_applications_status on applications (status);

-- Migration guard: CREATE TABLE IF NOT EXISTS above is a no-op on a database that
-- already has this table from an earlier deploy, so new columns need an explicit
-- ADD COLUMN IF NOT EXISTS too (schema.sql is re-applied idempotently on every startup).
alter table applications add column if not exists last_cancel_message_id bigint;

create table if not exists messages (
    id bigserial primary key,
    application_id bigint not null references applications(id) on delete cascade,
    sender text not null check (sender in ('user','assistant','system')),
    type text not null check (type in ('text','voice')),
    raw_text text,
    language text,
    telegram_message_id bigint,
    created_at timestamptz not null default now()
);

create index if not exists idx_messages_application_created on messages (application_id, created_at);

create table if not exists voice_files (
    id bigserial primary key,
    message_id bigint not null references messages(id) on delete cascade,
    telegram_file_id text not null,
    duration_seconds int,
    transcript_confidence real
);

create table if not exists attachments (
    id bigserial primary key,
    application_id bigint not null references applications(id) on delete cascade,
    type text not null check (type in ('photo','document','link')),
    telegram_file_id text,
    url text,
    original_filename text,
    mime_type text,
    created_at timestamptz not null default now()
);

create index if not exists idx_attachments_application on attachments (application_id);

create table if not exists admin_notes (
    id bigserial primary key,
    application_id bigint not null references applications(id) on delete cascade,
    admin_id bigint not null,
    text text not null,
    created_at timestamptz not null default now()
);

create table if not exists admin_messages (
    id bigserial primary key,
    application_id bigint references applications(id) on delete cascade,
    direction text not null check (direction in ('admin_to_client','client_to_admin')),
    text text not null,
    telegram_message_id bigint,
    created_at timestamptz not null default now()
);

create table if not exists events (
    id bigserial primary key,
    application_id bigint references applications(id) on delete set null,
    user_id bigint references users(id) on delete set null,
    event_type text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_events_type_created on events (event_type, created_at);

-- v1.2: post-completion revisions (TZ p.67-68). Independent status from applications.status.
create table if not exists revisions (
    id bigserial primary key,
    application_id bigint not null references applications(id) on delete cascade,
    user_id bigint not null references users(id) on delete cascade,
    raw_text text not null,
    client_understanding_text text,
    ai_summary text,
    status revision_status not null default 'new',
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

-- Mandatory per TZ p.68.8: hot path for counting open revisions / numbering.
create index if not exists idx_revisions_application_status on revisions (application_id, status);
