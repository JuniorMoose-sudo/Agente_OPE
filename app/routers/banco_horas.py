"""Endpoints de leitura do painel-ope (banco de horas, HE, infrações).

Async e somente leitura do Postgres já sincronizado — nunca chamam a API
externa dentro do tempo de resposta.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.banco_horas_semanal import BancoHorasSemanal
from app.models.roster_tecnico import RosterTecnico
from app.schemas.banco_horas import AnalisesResumo, RosterResumo, StatusCookie
from app.services.painel_ope_client import PainelOpeClient

router = APIRouter(prefix="/banco-horas", tags=["banco-horas"])


def _payload_totais(payload: dict) -> tuple[float | None, int | None, int | None, int | None, int | None]:
    """Extrai totais do payload bruto do /analises (sem quebrar se faltar chave)."""
    totais = payload.get("totais") or {}
    return (
        totais.get("heHoras"),
        totais.get("infracoes"),
        totais.get("tecnicos"),
        totais.get("tecComHE"),
        totais.get("tecComInfr"),
    )


@router.get("/analises", response_model=AnalisesResumo)
def analises(
    setor: str,
    de: date | None = Query(None, description="Início do período (YYYY-MM-DD)"),
    ate: date | None = Query(None, description="Fim do período (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> AnalisesResumo:
    """Snapshot de banco de horas/HE/infrações de um setor num período."""
    filtros = [BancoHorasSemanal.setor == setor]
    if de:
        filtros.append(BancoHorasSemanal.semana_de == de)
    if ate:
        filtros.append(BancoHorasSemanal.semana_ate == ate)

    registro = db.execute(
        select(BancoHorasSemanal).where(*filtros).order_by(BancoHorasSemanal.semana_de.desc())
    ).scalars().first()

    if not registro:
        raise HTTPException(status_code=404, detail=f"Sem snapshot do setor {setor} para o período.")

    he_horas, infracoes, tecnicos, tec_he, tec_infr = _payload_totais(registro.payload or {})
    return AnalisesResumo(
        setor=registro.setor,
        semana_de=registro.semana_de,
        semana_ate=registro.semana_ate,
        total_he_horas=he_horas,
        total_infracoes=infracoes,
        tecnicos=tecnicos,
        tec_com_he=tec_he,
        tec_com_infracao=tec_infr,
    )


@router.get("/roster", response_model=RosterResumo)
def roster(setor: str, db: Session = Depends(get_db)) -> RosterResumo:
    """Lista de técnicos ativos de um setor (validador de nomes)."""
    nomes = db.scalars(
        select(RosterTecnico.tecnico)
        .where(RosterTecnico.setor == setor)
        .order_by(RosterTecnico.tecnico)
    ).all()
    if not nomes:
        raise HTTPException(status_code=404, detail=f"Roster do setor {setor} vazio (sincronize antes).")
    return RosterResumo(setor=setor, tecnicos=list(nomes))


@router.get("/status-cookie", response_model=StatusCookie)
def status_cookie() -> StatusCookie:
    """Estado do cookie do painel-ope: presente/ausente e dias até expirar."""
    if not settings.ope_session_cookie:
        return StatusCookie(configurado=False)
    try:
        dias = PainelOpeClient().dias_para_expirar()
    except Exception:
        dias = None
    return StatusCookie(configurado=True, expira_em_dias=dias)
