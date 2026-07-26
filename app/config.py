from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # WhatsApp
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = "1186710814528940"
    whatsapp_verify_token: str = "petpulse_wh_9f3a7c2e1b6d4581"
    whatsapp_app_secret: str = ""
    whatsapp_api_version: str = "v21.0"

    # OpenAI
    openai_api_key: str = ""
    openai_agent_model: str = "gpt-5.4-mini"
    openai_reasoning_model: str = "gpt-5.4"
    openai_audio_model: str = "gpt-audio"
    openai_agent_max_tokens: int = 5600
    openai_agent_max_iterations: int = 10

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Google Calendar (OAuth2 user credentials — a bare service account cannot
    # generate Google Meet links, confirmed live; see google_calendar.py docstring
    # and scripts/get_google_refresh_token.py for one-time setup)
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    google_calendar_refresh_token: str = ""
    google_calendar_id: str = "primary"

    log_level: str = "INFO"
    timezone: str = "Asia/Kolkata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
