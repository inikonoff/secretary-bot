from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_id: int

    database_url: str

    supabase_url: str = ""
    supabase_key: str = ""

    groq_api_key: str
    openrouter_api_key: str = ""

    groq_model_interview: str = "openai/gpt-oss-20b"
    groq_model_final: str = "openai/gpt-oss-120b"
    groq_whisper_model: str = "whisper-large-v3"

    openrouter_model_interview: str = "openai/gpt-oss-20b:free"
    openrouter_model_final: str = "openai/gpt-oss-120b"

    webhook_base_url: str
    webhook_path: str = "/webhook"
    webhook_secret: str
    port: int = 8080

    telegraph_help_url: str = ""

    debounce_seconds: float = 3.0
    rate_limit_messages: int = 3
    rate_limit_window_seconds: float = 60.0
    max_text_length: int = 800
    max_voice_seconds: int = 60
    max_file_mb: int = 5
    max_add_info_cycles: int = 3
    clarifying_questions_soft_limit: int = 3
    same_topic_abandon_threshold: int = 3
    incomplete_session_reminder_hours: float = 24.0

    log_level: str = "INFO"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
