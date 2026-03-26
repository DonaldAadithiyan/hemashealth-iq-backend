from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    openai_api_key: str

    # Supabase — leave empty while using mock_db.
    # Fill these in when your real DB is ready.
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Optional translation
    google_cloud_project: str = ""
    google_application_credentials: str = ""

    app_env: str = "development"
    allowed_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()