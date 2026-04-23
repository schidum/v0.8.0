# app/config.py
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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

    # Приложение
    APP_TITLE: str = "Агро API — Точное земледелие"
    APP_VERSION: str = "0.3.2"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()