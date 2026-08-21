"""State machine, statuses and other fixed vocabularies (TZ v1.1 p.43, p.58)."""

# applications.state — durable FSM state, source of truth in DB
STATE_IDLE = "idle"
STATE_CREATING = "creating"
STATE_WAITING_INITIAL_DESCRIPTION = "waiting_initial_description"
STATE_INTERVIEW = "interview"
STATE_WAITING_DEADLINE = "waiting_deadline"
STATE_UNDERSTANDING = "understanding"
STATE_ADDING_INFORMATION = "adding_information"
STATE_WAITING_CONFIRMATION = "waiting_confirmation"
STATE_FINALIZING = "finalizing"
STATE_FINALIZED = "finalized"
STATE_CANCELLED = "cancelled"

TERMINAL_STATES = {STATE_FINALIZED, STATE_CANCELLED}

# applications.status — admin-facing pipeline (TZ p.43)
STATUS_NEW = "new"
STATUS_VIEWED = "viewed"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_REJECTED = "rejected"

STATUS_EMOJI = {
    STATUS_NEW: "🆕",
    STATUS_VIEWED: "👀",
    STATUS_IN_PROGRESS: "🔧",
    STATUS_COMPLETED: "✅",
    STATUS_REJECTED: "❌",
}

STATUS_LABELS_RU = {
    STATUS_NEW: "Новая",
    STATUS_VIEWED: "Просмотрена",
    STATUS_IN_PROGRESS: "В работе",
    STATUS_COMPLETED: "Завершена",
    STATUS_REJECTED: "Отклонена",
}

# revisions.status — independent of applications.status (TZ v1.1 p.67-68.6)
REVISION_STATUS_NEW = "new"
REVISION_STATUS_VIEWED = "viewed"
REVISION_STATUS_IN_PROGRESS = "in_progress"
REVISION_STATUS_DONE = "done"

REVISION_STATUS_EMOJI = {
    REVISION_STATUS_NEW: "🆕",
    REVISION_STATUS_VIEWED: "👀",
    REVISION_STATUS_IN_PROGRESS: "🔧",
    REVISION_STATUS_DONE: "✅",
}

REVISION_STATUS_LABELS_RU = {
    REVISION_STATUS_NEW: "Новая",
    REVISION_STATUS_VIEWED: "Просмотрена",
    REVISION_STATUS_IN_PROGRESS: "В работе",
    REVISION_STATUS_DONE: "Готово",
}

MESSAGE_SENDER_USER = "user"
MESSAGE_SENDER_ASSISTANT = "assistant"
MESSAGE_SENDER_SYSTEM = "system"

MESSAGE_TYPE_TEXT = "text"
MESSAGE_TYPE_VOICE = "voice"

ATTACHMENT_PHOTO = "photo"
ATTACHMENT_DOCUMENT = "document"
ATTACHMENT_LINK = "link"

ADMIN_MESSAGE_ADMIN_TO_CLIENT = "admin_to_client"
ADMIN_MESSAGE_CLIENT_TO_ADMIN = "client_to_admin"

EVENT_STATUS_CHANGE = "status_change"
EVENT_LLM_ERROR = "llm_error"
EVENT_FALLBACK_TRIGGERED = "fallback_triggered"
EVENT_RATE_LIMIT_HIT = "rate_limit_hit"
EVENT_POSSIBLE_ABUSE = "possible_abuse"
EVENT_REMINDER_SENT = "reminder_sent"
EVENT_REVISION_CREATED = "revision_created"
EVENT_OUT_OF_SCOPE = "out_of_scope"

AI_ACTION_ASK = "ask"
AI_ACTION_UNDERSTANDING = "understanding"
AI_ACTION_WAIT_INPUT = "wait_input"
AI_ACTION_ERROR = "error"

QUESTION_IMPORTANCE_CRITICAL = "critical"
QUESTION_IMPORTANCE_USEFUL = "useful"
QUESTION_IMPORTANCE_OPTIONAL = "optional"
