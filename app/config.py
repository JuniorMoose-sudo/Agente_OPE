from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações lidas de variáveis de ambiente (.env, nunca commitado).

    As chaves do Proxxima e o cookie do painel-ope são segredos: ficam apenas
    em ambiente, nunca em código ou logs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/agente_ope"

    proxxima_user: str | None = None
    proxxima_password: str | None = None
    proxxima_lookback_days: int = 30
    proxxima_sync_interval_seconds: int = 1800
    ope_session_cookie: str | None = None

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


settings = Settings()
