"""Repository layer: thin, explicit SQL wrappers around asyncpg. One class per entity (TZ v1.1 p.59)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg


def _row(row: Optional[asyncpg.Record]) -> Optional[dict]:
    return dict(row) if row is not None else None


class UsersRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_or_create(self, telegram_id: int, username: str | None, first_name: str | None) -> dict:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                """
                insert into users (telegram_id, username, first_name, last_active_at)
                values ($1, $2, $3, now())
                on conflict (telegram_id) do update
                    set username = excluded.username,
                        first_name = excluded.first_name,
                        last_active_at = now()
                returning *
                """,
                telegram_id, username, first_name,
            )
            return _row(row)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow("select * from users where telegram_id = $1", telegram_id)
        return _row(row)

    async def touch_last_active(self, user_id: int) -> None:
        await self.pool.execute("update users set last_active_at = now() where id = $1", user_id)

    async def set_language(self, user_id: int, language_code: str) -> None:
        await self.pool.execute("update users set language_code = $1 where id = $2", language_code, user_id)

    async def set_blocked(self, user_id: int, blocked: bool) -> None:
        await self.pool.execute(
            "update users set is_blocked = $1, blocked_at = case when $1 then now() else null end where id = $2",
            blocked, user_id,
        )

    async def is_blocked(self, telegram_id: int) -> bool:
        val = await self.pool.fetchval("select is_blocked from users where telegram_id = $1", telegram_id)
        return bool(val)

    async def list_clients(self, limit: int = 50, offset: int = 0) -> list[dict]:
        rows = await self.pool.fetch(
            """
            select u.*,
                   count(a.id) as applications_count,
                   max(a.created_at) as last_application_at
            from users u
            left join applications a on a.user_id = u.id
            group by u.id
            order by u.last_active_at desc
            limit $1 offset $2
            """,
            limit, offset,
        )
        return [dict(r) for r in rows]

    async def list_blocked(self) -> list[dict]:
        rows = await self.pool.fetch("select * from users where is_blocked = true order by blocked_at desc")
        return [dict(r) for r in rows]

    async def get_client_card(self, user_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow("select * from users where id = $1", user_id)
        return _row(row)


class ApplicationsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, user_id: int, state: str) -> dict:
        row = await self.pool.fetchrow(
            """
            insert into applications (user_id, state, status, project_context)
            values ($1, $2, 'new', '{}'::jsonb)
            returning *
            """,
            user_id, state,
        )
        return _row(row)

    async def get(self, application_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow("select * from applications where id = $1", application_id)
        return _row(row)

    async def get_incomplete_for_user(self, user_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow(
            """
            select * from applications
            where user_id = $1 and state not in ('finalized', 'cancelled')
            order by created_at desc
            limit 1
            """,
            user_id,
        )
        return _row(row)

    async def list_for_user(self, user_id: int) -> list[dict]:
        # Admin-facing: an unconfirmed session "не считается полноценной заявкой" (TZ p.55)
        # and must not show up here, even though it already exists as a DB row.
        rows = await self.pool.fetch(
            "select * from applications where user_id = $1 and state = 'finalized' order by created_at desc",
            user_id,
        )
        return [dict(r) for r in rows]

    async def list_finalized_for_user(self, user_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "select * from applications where user_id = $1 and state = 'finalized' order by created_at desc",
            user_id,
        )
        return [dict(r) for r in rows]

    async def update_state(self, application_id: int, state: str) -> None:
        await self.pool.execute(
            "update applications set state = $1, updated_at = now() where id = $2", state, application_id
        )

    async def update_status(self, application_id: int, status: str) -> None:
        await self.pool.execute(
            "update applications set status = $1, updated_at = now() where id = $2", status, application_id
        )

    async def update_project_context(self, application_id: int, project_context: dict) -> None:
        await self.pool.execute(
            "update applications set project_context = $1::jsonb, updated_at = now() where id = $2",
            json.dumps(project_context), application_id,
        )

    async def update_client_understanding(self, application_id: int, text: str) -> None:
        await self.pool.execute(
            "update applications set client_understanding_text = $1, updated_at = now() where id = $2",
            text, application_id,
        )

    async def set_deadline_text(self, application_id: int, deadline_text: str) -> None:
        await self.pool.execute(
            "update applications set deadline_text = $1, updated_at = now() where id = $2",
            deadline_text, application_id,
        )

    async def set_last_cancel_message_id(self, application_id: int, message_id: int | None) -> None:
        await self.pool.execute(
            "update applications set last_cancel_message_id = $1 where id = $2", message_id, application_id
        )

    async def set_pending_understanding_message(self, application_id: int, text: str | None) -> None:
        await self.pool.execute(
            "update applications set pending_understanding_message = $1, updated_at = now() where id = $2",
            text, application_id,
        )

    async def increment_add_info_count(self, application_id: int) -> int:
        return await self.pool.fetchval(
            "update applications set add_info_count = add_info_count + 1, updated_at = now() "
            "where id = $1 returning add_info_count",
            application_id,
        )

    async def increment_clarifying_questions_count(self, application_id: int) -> int:
        return await self.pool.fetchval(
            "update applications set clarifying_questions_count = clarifying_questions_count + 1, "
            "updated_at = now() where id = $1 returning clarifying_questions_count",
            application_id,
        )

    async def update_topic_tracking(self, application_id: int, topic: str | None, same_topic_retry_count: int) -> None:
        await self.pool.execute(
            "update applications set current_question_topic = $1, same_topic_retry_count = $2, "
            "updated_at = now() where id = $3",
            topic, same_topic_retry_count, application_id,
        )

    async def set_flagged_abuse(self, application_id: int) -> None:
        await self.pool.execute(
            "update applications set flagged_as_abuse = true, updated_at = now() where id = $1", application_id
        )

    async def finalize(self, application_id: int, tz_markdown_path: str, tz_markdown_content: str) -> None:
        await self.pool.execute(
            """
            update applications
            set state = 'finalized',
                confirmed_at = now(),
                updated_at = now(),
                tz_markdown_path = $1,
                tz_markdown_content = $2
            where id = $3
            """,
            tz_markdown_path, tz_markdown_content, application_id,
        )

    async def cancel(self, application_id: int) -> None:
        await self.pool.execute(
            "update applications set state = 'cancelled', updated_at = now() where id = $1", application_id
        )

    async def mark_reminder_sent(self, application_id: int) -> None:
        await self.pool.execute(
            "update applications set reminder_sent_at = now() where id = $1", application_id
        )

    async def list_by_status(self, status: str | None, limit: int = 20, offset: int = 0) -> list[dict]:
        # Same "not a real application until confirmed" rule as list_for_user above.
        if status:
            rows = await self.pool.fetch(
                "select a.*, u.username, u.first_name, u.telegram_id from applications a "
                "join users u on u.id = a.user_id "
                "where a.state = 'finalized' and a.status = $1 order by a.created_at desc limit $2 offset $3",
                status, limit, offset,
            )
        else:
            rows = await self.pool.fetch(
                "select a.*, u.username, u.first_name, u.telegram_id from applications a "
                "join users u on u.id = a.user_id "
                "where a.state = 'finalized' "
                "order by a.created_at desc limit $1 offset $2",
                limit, offset,
            )
        return [dict(r) for r in rows]

    async def get_with_client(self, application_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow(
            "select a.*, u.username, u.first_name, u.telegram_id, u.language_code from applications a "
            "join users u on u.id = a.user_id where a.id = $1",
            application_id,
        )
        return _row(row)

    async def list_stale_incomplete(self, older_than_hours: float) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        rows = await self.pool.fetch(
            """
            select a.*, u.telegram_id from applications a
            join users u on u.id = a.user_id
            where a.state not in ('finalized', 'cancelled')
              and a.reminder_sent_at is null
              and a.updated_at < $1
            """,
            cutoff,
        )
        return [dict(r) for r in rows]

    async def stats_overall(self) -> dict:
        # Same "not a real application until confirmed" rule — draft sessions must not
        # inflate the admin's counters any more than they should appear in the lists above.
        row = await self.pool.fetchrow(
            """
            select
                (select count(*) from users) as clients,
                (select count(*) from applications where state = 'finalized') as applications,
                (select count(*) from applications where state = 'finalized' and status = 'new') as new,
                (select count(*) from applications where state = 'finalized' and status = 'viewed') as viewed,
                (select count(*) from applications where state = 'finalized' and status = 'in_progress') as in_progress,
                (select count(*) from applications where state = 'finalized' and status = 'completed') as completed,
                (select count(*) from applications where state = 'finalized' and status = 'rejected') as rejected,
                (select count(*) from users where is_blocked = true) as blocked
            """
        )
        return _row(row)

    async def stats_period(self, days: int) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        row = await self.pool.fetchrow(
            """
            select
                (select count(*) from users where created_at >= $1) as new_clients,
                (select count(*) from applications where state = 'finalized' and confirmed_at >= $1) as new_applications,
                (select count(*) from applications where state = 'finalized' and status = 'completed' and updated_at >= $1) as completed
            """,
            since,
        )
        return _row(row)


class MessagesRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(
        self,
        application_id: int,
        sender: str,
        type_: str,
        raw_text: str | None,
        language: str | None,
        telegram_message_id: int | None,
    ) -> dict:
        row = await self.pool.fetchrow(
            """
            insert into messages (application_id, sender, type, raw_text, language, telegram_message_id)
            values ($1, $2, $3, $4, $5, $6)
            returning *
            """,
            application_id, sender, type_, raw_text, language, telegram_message_id,
        )
        return _row(row)

    async def set_language_for_ids(self, message_ids: list[int], language: str) -> None:
        if not message_ids:
            return
        await self.pool.execute("update messages set language = $1 where id = any($2::bigint[])", language, message_ids)

    async def recent_for_application(self, application_id: int, limit: int = 6) -> list[dict]:
        rows = await self.pool.fetch(
            """
            select * from (
                select * from messages where application_id = $1
                order by created_at desc limit $2
            ) sub order by created_at asc
            """,
            application_id, limit,
        )
        return [dict(r) for r in rows]

    async def all_for_application(self, application_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "select * from messages where application_id = $1 order by created_at asc", application_id
        )
        return [dict(r) for r in rows]


class VoiceFilesRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(self, message_id: int, telegram_file_id: str, duration_seconds: int | None,
                   transcript_confidence: float | None) -> dict:
        row = await self.pool.fetchrow(
            """
            insert into voice_files (message_id, telegram_file_id, duration_seconds, transcript_confidence)
            values ($1, $2, $3, $4)
            returning *
            """,
            message_id, telegram_file_id, duration_seconds, transcript_confidence,
        )
        return _row(row)

    async def list_for_application(self, application_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            """
            select vf.* from voice_files vf
            join messages m on m.id = vf.message_id
            where m.application_id = $1
            order by vf.id asc
            """,
            application_id,
        )
        return [dict(r) for r in rows]


class AttachmentsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(self, application_id: int, type_: str, telegram_file_id: str | None, url: str | None,
                   original_filename: str | None, mime_type: str | None) -> dict:
        row = await self.pool.fetchrow(
            """
            insert into attachments (application_id, type, telegram_file_id, url, original_filename, mime_type)
            values ($1, $2, $3, $4, $5, $6)
            returning *
            """,
            application_id, type_, telegram_file_id, url, original_filename, mime_type,
        )
        return _row(row)

    async def list_for_application(self, application_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "select * from attachments where application_id = $1 order by created_at asc", application_id
        )
        return [dict(r) for r in rows]


class AdminNotesRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(self, application_id: int, admin_id: int, text: str) -> dict:
        row = await self.pool.fetchrow(
            "insert into admin_notes (application_id, admin_id, text) values ($1, $2, $3) returning *",
            application_id, admin_id, text,
        )
        return _row(row)

    async def list_for_application(self, application_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "select * from admin_notes where application_id = $1 order by created_at asc", application_id
        )
        return [dict(r) for r in rows]


class AdminMessagesRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(self, application_id: int | None, direction: str, text: str, telegram_message_id: int | None) -> dict:
        row = await self.pool.fetchrow(
            """
            insert into admin_messages (application_id, direction, text, telegram_message_id)
            values ($1, $2, $3, $4)
            returning *
            """,
            application_id, direction, text, telegram_message_id,
        )
        return _row(row)

    async def list_for_application(self, application_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "select * from admin_messages where application_id = $1 order by created_at asc", application_id
        )
        return [dict(r) for r in rows]


class EventsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def log(self, event_type: str, application_id: int | None = None, user_id: int | None = None,
                   payload: dict[str, Any] | None = None) -> None:
        await self.pool.execute(
            "insert into events (application_id, user_id, event_type, payload) values ($1, $2, $3, $4::jsonb)",
            application_id, user_id, event_type, json.dumps(payload or {}),
        )


class RevisionsRepo:
    """Post-completion revisions (TZ v1.1 p.67-68) — independent from the applications state machine."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(
        self, application_id: int, user_id: int, raw_text: str, client_understanding_text: str, ai_summary: str
    ) -> dict:
        row = await self.pool.fetchrow(
            """
            insert into revisions (application_id, user_id, raw_text, client_understanding_text, ai_summary, status)
            values ($1, $2, $3, $4, $5, 'new')
            returning *
            """,
            application_id, user_id, raw_text, client_understanding_text, ai_summary,
        )
        return _row(row)

    async def get(self, revision_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow("select * from revisions where id = $1", revision_id)
        return _row(row)

    async def list_for_application(self, application_id: int) -> list[dict]:
        rows = await self.pool.fetch(
            "select * from revisions where application_id = $1 order by created_at asc", application_id
        )
        return [dict(r) for r in rows]

    async def update_status(self, revision_id: int, status: str) -> None:
        if status == "done":
            await self.pool.execute(
                "update revisions set status = $1, completed_at = now() where id = $2", status, revision_id
            )
        else:
            await self.pool.execute("update revisions set status = $1 where id = $2", status, revision_id)

    async def get_numbering(self, application_id: int, revision_id: int) -> tuple[int, int]:
        """Returns (1-indexed creation-order position, count of currently open revisions) — TZ p.68.5."""
        revisions = await self.list_for_application(application_id)
        rank = next((i + 1 for i, r in enumerate(revisions) if r["id"] == revision_id), 0)
        total_open = sum(1 for r in revisions if r["status"] != "done")
        return rank, total_open


class Repo:
    """Facade bundling all repositories, injected into handlers as a single dependency."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.users = UsersRepo(pool)
        self.applications = ApplicationsRepo(pool)
        self.messages = MessagesRepo(pool)
        self.voice_files = VoiceFilesRepo(pool)
        self.attachments = AttachmentsRepo(pool)
        self.admin_notes = AdminNotesRepo(pool)
        self.admin_messages = AdminMessagesRepo(pool)
        self.events = EventsRepo(pool)
        self.revisions = RevisionsRepo(pool)
