from datetime import date

from pydantic import BaseModel


class AnalisesResumo(BaseModel):
    """Resumo de um snapshot semanal do painel-ope (lido do Postgres)."""

    setor: str
    semana_de: date
    semana_ate: date
    total_he_horas: float | None = None
    total_infracoes: int | None = None
    tecnicos: int | None = None
    tec_com_he: int | None = None
    tec_com_infracao: int | None = None


class RosterResumo(BaseModel):
    setor: str
    tecnicos: list[str]


class StatusCookie(BaseModel):
    configurado: bool
    expira_em_dias: int | None = None
