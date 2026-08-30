"""Job de sincronização do banco de horas — planilha pública (sem painel-ope).

Substitui o painel-ope como fonte de banco de horas/HE. Lê o CSV público da aba
``HISTORICO_REG03`` (contém CAMPINA GRANDE e LAGOA SECA) e faz upsert em
``banco_horas_saldo``, chave única (tecnico, unidade, data).

Job síncrono agendado via APScheduler (diário), fora do ciclo de request.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.banco_horas_saldo import BancoHorasSaldo
from app.services import banco_horas_sheets_client as sheets_client

logger = logging.getLogger(__name__)

UNIDADES_ALVO = settings.banco_horas_unidades

CAMPOS_MODELO = (
    "tecnico",
    "unidade",
    "data",
    "saldo",
    "cargo",
    "tipo",
    "coordenador",
    "supervisor",
    "variacao",
    "status",
)


def _montar_registros(linhas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filtra unidades-alvo e converte linhas brutas em registros do modelo.

    Função pura (testável sem banco): retorna (registros, estatísticas).
    Linhas fora das unidades, sem DATA ou sem SALDO são descartadas e contadas.
    """
    registros: list[dict[str, Any]] = []
    stats = {
        "processadas": len(linhas),
        "gravadas": 0,
        "ignoradas_outra_unidade": 0,
        "ignoradas_sem_nome": 0,
        "ignoradas_sem_data": 0,
        "ignoradas_sem_saldo": 0,
        "por_unidade": {},
    }
    for linha in linhas:
        unidade = str(linha.get("UNIDADE") or "").strip().upper()
        if unidade not in UNIDADES_ALVO:
            stats["ignoradas_outra_unidade"] += 1
            continue
        nome = str(linha.get("NOME") or "").strip()
        if not nome:
            stats["ignoradas_sem_nome"] += 1
            continue
        data = sheets_client.parse_data_br(linha.get("DATA"))
        if not data:
            stats["ignoradas_sem_data"] += 1
            continue
        saldo = sheets_client.parse_saldo_br(linha.get("SALDO"))
        if saldo is None:
            stats["ignoradas_sem_saldo"] += 1
            continue
        registros.append(
            {
                "tecnico": nome,
                "unidade": unidade,
                "data": datetime.combine(data, datetime.min.time()),
                "saldo": saldo,
                "cargo": sheets_client._texto_ou_none(linha.get("CARGO")),
                "tipo": sheets_client._texto_ou_none(linha.get("TIPO")),
                "coordenador": sheets_client._texto_ou_none(linha.get("COORDENADOR")),
                "supervisor": sheets_client._texto_ou_none(linha.get("SUPERVISOR")),
                "variacao": sheets_client._texto_ou_none(linha.get("VARIACAO")),
                "status": sheets_client._texto_ou_none(linha.get("STATUS")),
            }
        )
        stats["por_unidade"][unidade] = stats["por_unidade"].get(unidade, 0) + 1
    stats["gravadas"] = len(registros)
    return registros, stats


def _sync_registros(db: Session, registros: list[dict[str, Any]]) -> int:
    """Upsert chave (tecnico, unidade, data). Retorna quantos executou."""
    for reg in registros:
        stmt = pg_insert(BancoHorasSaldo).values(**{k: reg[k] for k in CAMPOS_MODELO})
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                BancoHorasSaldo.tecnico,
                BancoHorasSaldo.unidade,
                BancoHorasSaldo.data,
            ],
            set_={campo: stmt.excluded[campo] for campo in CAMPOS_MODELO},
        )
        db.execute(stmt)
    db.commit()
    return len(registros)


def sync_banco_horas_saldo(url: str | None = None) -> dict[str, Any]:
    """Ponto de entrada do job: baixa o CSV público e faz upsert."""
    db = SessionLocal()
    try:
        client = sheets_client.BancoHorasSheetsClient(url=url)
        linhas = client.fetch_saldo()
        registros, stats = _montar_registros(linhas)
        stats["upsert_ok"] = _sync_registros(db, registros)
        logger.info("[banco-horas] sync concluído: %s", stats)
        return stats
    finally:
        db.close()


_scheduler = None


def start_scheduler() -> None:
    """Agenda o sync do banco de horas (diário, fonte pública, sem credencial)."""
    global _scheduler
    if _scheduler is not None:
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        sync_banco_horas_saldo,
        "interval",
        days=1,
        id="sync_banco_horas_saldo",
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )
    _scheduler.start()
    logger.info("[banco-horas] sync diário agendado (unidades: %s)", ", ".join(UNIDADES_ALVO))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None