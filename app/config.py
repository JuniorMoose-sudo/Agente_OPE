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
    # Cookie de sessão do painel Operações (operacoes.proxxima.net, bl_session)
    # — recorrência analítica por unidade. Zoho SSO: sem usuário/senha de API,
    # o acesso é pelo cookie do navegador (mesmo padrão do painel-ope).
    operacoes_session_cookie: str | None = None

    # Token de acesso à própria API (Sprint 5) — enviado pelo plugin do agente
    # como `Authorization: Bearer <token>`. Nunca hardcoded, só via env.
    ops_api_token: str | None = None

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    sheets_service_account_json: str | None = None
    sheets_service_account_file: str | None = None
    sheets_spreadsheet_url: str | None = None
    sheets_aba_inspecao: str = "Inspecao"

    # Banco de Horas — Google Sheets PUBLICADA (web, sem cookie). Substitui o
    # painel-ope como fonte de banco de horas/HE. URL pública CSV da aba
    # HISTORICO_REG03 (contém CAMPINA GRANDE e LAGOA SECA).
    banco_horas_saldo_url: str = (
        "https://docs.google.com/spreadsheets/d/e/"
        "2PACX-1vSk5U4vu-eS4QBbIH0pIAKAWCSGx10mnjhCo0EqgvZSqRU5UFfqclBiXCFmdar_d_G_NzCJQY-Wp663/"
        "pub?gid=2049164456&single=true&output=csv"
    )
    banco_horas_unidades: tuple[str, ...] = ("CAMPINA GRANDE", "LAGOA SECA")

    # TOTVS Analytics (GoodData) — cookie de sessão do navegador
    totvs_sst_cookie: str | None = None

    # Diretório onde os relatórios .docx são salvos
    dir_relatorios: str = "relatorios"


settings = Settings()
