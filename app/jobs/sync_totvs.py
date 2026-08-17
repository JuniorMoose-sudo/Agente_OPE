"""Job de sincronização do TOTVS Analytics (GoodData) — KPIs e métricas.

Job síncrono agendado (APScheduler), fora do ciclo de request dos endpoints.
Sincroniza os dashboards conhecidos:

- KPI OPERAÇÕES (dashboard 124470, report 4890627): Reparos até 24h, Encerrados, %
- PREMIAÇÃO SUPERVISOR (dashboard 2278082, report 1464793): dados detalhados por técnico
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.metrica_totvs import MetricaTotvs
from app.services.telegram import avisar_telegram
from app.services.totvs_client import (
    DASHBOARD_KPI,
    DASHBOARD_PREMIACAO_SUPERVISOR,
    REPORT_KPI_REPAROS,
    REPORT_PREMIACAO_SUPERVISOR,
    TotvsAuthError,
    TotvsClient,
    TotvsError,
)

logger = logging.getLogger(__name__)

# Reports a sincronizar: (dashboard_id, report_id, titulo)
REPORTS_A_SINCRONIZAR = [
    (DASHBOARD_KPI, REPORT_KPI_REPAROS, "KPIs Reparos - Operações Geral"),
    (DASHBOARD_PREMIACAO_SUPERVISOR, REPORT_PREMIACAO_SUPERVISOR, "Premiação Supervisor - Detalhado"),
]


def _sync_report(db: Session, client: TotvsClient, dashboard_id: str, report_id: str, titulo: str, hoje: date) -> dict[str, Any]:
    """Executa um report, busca dataResult e grava no banco. Retorna contagens."""
    exec_result = client.execute_report(report_id, dashboard_id)
    data_path = exec_result.get("execResult", {}).get("dataResult")
    if not data_path:
        logger.warning("[totvs] report %s (%s) não retornou dataResult", titulo, report_id)
        return {"report": titulo, "status": "sem_data"}

    xtab = client.get_data_result(data_path)
    report_view = exec_result.get("execResult", {}).get("reportView", {})
    report_name = report_view.get("reportName", titulo)

    stmt = pg_insert(MetricaTotvs).values(
        dashboard_id=dashboard_id,
        report_id=report_id,
        dashboard_titulo=titulo,
        report_titulo=report_name,
        data_referencia=hoje,
        payload=xtab,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            MetricaTotvs.dashboard_id,
            MetricaTotvs.report_id,
            MetricaTotvs.data_referencia,
        ],
        set_={"payload": stmt.excluded.payload, "report_titulo": stmt.excluded.report_titulo},
    )
    db.execute(stmt)
    db.commit()

    parsed = TotvsClient.parse_xtab_data(xtab.get("xtab_data", {}))
    return {"report": titulo, "status": "ok", "linhas": len(parsed)}


def sync_totvs() -> dict[str, Any]:
    """Ponto de entrada do job: sincroniza todos os reports conhecidos."""
    if not settings.totvs_sst_cookie:
        logger.info("[totvs] TOTVS_SST_COOKIE não configurado — sync ignorado.")
        return {"status": "ignorado"}

    hoje = date.today()
    db = SessionLocal()
    try:
        with TotvsClient() as client:
            resultados: dict[str, Any] = {"data": hoje.isoformat()}
            for dashboard_id, report_id, titulo in REPORTS_A_SINCRONIZAR:
                try:
                    resultado = _sync_report(db, client, dashboard_id, report_id, titulo, hoje)
                    resultados[report_id] = resultado
                except TotvsError as exc:
                    logger.error("[totvs] Erro ao sincronizar %s: %s", titulo, exc)
                    resultados[report_id] = {"report": titulo, "status": "erro", "erro": str(exc)}
    except TotvsAuthError as exc:
        avisar_telegram("⚠️ Falha de autenticação no TOTVS Analytics. Renove o cookie GDCAuthSST.")
        raise
    finally:
        db.close()

    logger.info("[totvs] %s", resultados)
    return resultados


_scheduler = None


def start_scheduler() -> None:
    """Agenda o sync do TOTVS Analytics (diário)."""
    global _scheduler
    if _scheduler is not None or not settings.totvs_sst_cookie:
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        sync_totvs,
        "interval",
        days=1,
        id="sync_totvs",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("[totvs] sync diário agendado")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
