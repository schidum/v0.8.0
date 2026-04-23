# app/config.py
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ==================== ENVIRONMENT ====================
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment: development, staging, production"
    )
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode"
    )

    # База данных
    DATABASE_URL: str = "sqlite+aiosqlite:///./agro.db"

    # JWT
    SECRET_KEY: str = Field(
        default=..., min_length=32,
        description="Сильный секрет (64+ символов)"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # ==================== RABBITMQ (для Windows 7 + 3.6.6) ====================
    RABBITMQ_URL: str = Field(
        default="amqp://guest:guest@localhost:5672//",
        description="URL вашего RabbitMQ 3.6.6 (по умолчанию guest/guest)"
    )

    # Backend результатов — rpc (работает через тот же RabbitMQ, Redis не нужен)
    CELERY_RESULT_BACKEND: str = "rpc://"

    # ==================== CORS CONFIGURATION ====================
    CORS_ORIGINS: str = Field(
        default="http://localhost:8000,http://127.0.0.1:8000",
        description="Comma-separated list of allowed origins for CORS"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )
    CORS_ALLOW_METHODS: list = Field(
        default=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        description="HTTP methods allowed in CORS requests"
    )
    CORS_ALLOW_HEADERS: list = Field(
        default=["Authorization", "Content-Type", "X-App-Client"],
        description="Headers allowed in CORS requests"
    )
    CORS_MAX_AGE: int = Field(
        default=600,
        description="Max age for CORS preflight cache (seconds)"
    )

    # Приложение
    APP_TITLE: str = "Агро API — Точное земледелие"
    APP_VERSION: str = "0.8.0"

    @property
    def cors_origins_list(self) -> list:
        """Parse CORS origins from comma-separated string."""
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        # Remove empty strings
        return [o for o in origins if o]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()