"""Endpoints de leitura do TOTVS Analytics (GoodData) — KPIs e métricas.

Async e somente leitura do Postgres já sincronizado — nunca chamam a API
externa dentro do tempo de resposta.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.metrica_totvs import MetricaTotvs
from app.services.totvs_client import TotvsClient

router = APIRouter(prefix="/totvs", tags=["totvs"])


@router.get("/kpi")
def kpi_operacoes(
    data: date | None = Query(None, description="Data de referência (YYYY-MM-DD). Padrão: hoje."),
    db: Session = Depends(get_db),
) -> dict:
    """KPIs de operação do TOTVS (Reparos até 24h, Encerrados, %)."""
    ref = data or date.today()
    registro = db.execute(
        select(MetricaTotvs)
        .where(
            MetricaTotvs.report_id == "4890627",
            MetricaTotvs.data_referencia == ref,
        )
        .order_by(MetricaTotvs.criado_em.desc())
    ).scalars().first()

    if not registro:
        raise HTTPException(status_code=404, detail=f"Sem KPI do TOTVS para {ref}.")

    xtab = (registro.payload or {}).get("xtab_data", {})
    dados_parseados = TotvsClient.parse_xtab_data(xtab)

    return {
        "data_referencia": ref.isoformat(),
        "report_titulo": registro.report_titulo,
        "dados": dados_parseados,
    }


@router.get("/premiacao")
def premiacao_supervisor(
    data: date | None = Query(None, description="Data de referência (YYYY-MM-DD). Padrão: hoje."),
    db: Session = Depends(get_db),
) -> dict:
    """Dados de premiação supervisor do TOTVS (detalhado por técnico)."""
    ref = data or date.today()
    registro = db.execute(
        select(MetricaTotvs)
        .where(
            MetricaTotvs.report_id == "1464793",
            MetricaTotvs.data_referencia == ref,
        )
        .order_by(MetricaTotvs.criado_em.desc())
    ).scalars().first()

    if not registro:
        raise HTTPException(status_code=404, detail=f"Sem premiação do TOTVS para {ref}.")

    xtab = (registro.payload or {}).get("xtab_data", {})
    dados_parseados = TotvsClient.parse_xtab_data(xtab)

    return {
        "data_referencia": ref.isoformat(),
        "report_titulo": registro.report_titulo,
        "dados": dados_parseados,
    }


@router.get("/pontuacao")
def pontuacao_tecnico(
    data: date | None = Query(None, description="Data de referência (YYYY-MM-DD). Padrão: hoje."),
    db: Session = Depends(get_db),
) -> dict:
    """Pontuação por técnico do TOTVS (média ou por dia)."""
    ref = data or date.today()
    # Busca qualquer report de pontuação (4890627=KPI, 1464793=Premiação, ou outros)
    registro = db.execute(
        select(MetricaTotvs)
        .where(
            MetricaTotvs.data_referencia == ref,
            MetricaTotvs.report_titulo.ilike("%pontua%"),
        )
        .order_by(MetricaTotvs.criado_em.desc())
    ).scalars().first()

    if not registro:
        raise HTTPException(status_code=404, detail=f"Sem dados de pontuação do TOTVS para {ref}.")

    xtab = (registro.payload or {}).get("xtab_data", {})
    dados_parseados = TotvsClient.parse_xtab_data(xtab)

    return {
        "data_referencia": ref.isoformat(),
        "report_titulo": registro.report_titulo,
        "dados": dados_parseados,
    }


@router.get("/status-cookie")
def status_cookie_totvs() -> dict:
    """Estado do cookie do TOTVS Analytics: presente/ausente."""
    configurado = bool(settings.totvs_sst_cookie)
    return {"configurado": configurado}
