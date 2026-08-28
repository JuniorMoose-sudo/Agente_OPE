"""Job de sincronização do Proxxima Connect para o Postgres.

Job síncrono agendado (APScheduler), fora do ciclo de request dos endpoints.
O mapeamento payload -> modelo foi validado contra dados reais (ver
``docs/progress.md``): ``numero_Obra`` é o número da OS, ``responsavel`` é o
técnico (nome completo em maiúsculas), ``grupo_Area`` é a unidade,
``status_Execucao`` é o status, e as datas vêm em formato brasileiro
``dd/mm/yyyy HH:MM``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.solicitacao_servico import SolicitacaoServico
from app.services.proxxima_client import ProxximaClient, ProxximaRequestError

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("America/Sao_Paulo")

DATE_FORMATS = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S")


def _parse_data_br(value: Any) -> datetime | None:
    """Converte data brasileira ``dd/mm/yyyy HH:MM`` para datetime aware."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TIMEZONE)
        except ValueError:
            continue
    logger.warning("Data no formato inesperado: %r (registro será gravado sem data)", value)
    return None


def _normalizar_os(numero_obra: Any) -> str | None:
    """``8762147/1`` -> ``8762147`` (chave de join com o Excel de recorrência)."""
    if numero_obra is None:
        return None
    texto = str(numero_obra).strip()
    if not texto:
        return None
    return texto.split("/")[0]


def _map_payload(servico: dict[str, Any]) -> dict[str, Any] | None:
    """Mapeia um registro do GetAll para as colunas de ``solicitacao_servico``.

    Retorna ``None`` quando não há número de OS (registro é ignorado).
    """
    os_key = _normalizar_os(servico.get("numero_Obra"))
    if os_key is None:
        return None

    return {
        "os": os_key,
        "os_original": str(servico.get("numero_Obra") or os_key),
        "unidade": servico.get("grupo_Area"),
        "natureza": servico.get("natureza"),
        "status": servico.get("status_Execucao"),
        "tecnico": servico.get("responsavel"),
        "abertura": _parse_data_br(servico.get("dataHora_Abertura_OS")),
        "venc": _parse_data_br(servico.get("dataHora_Vencimento_OS")),
        "sla_status": servico.get("sla"),
        "relatos": servico.get("observacao"),
        "payload": servico,
    }


def _deduplicar(mapeados: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mantém a última ocorrência de cada ``os_original`` (chave única).

    O GetAll pode retornar o mesmo ``numero_Obra`` mais de uma vez na
    mesma janela; como ``os_original`` é a chave de conflito do upsert,
    precisamos garantir unicidade dentro do lote.
    """
    por_chave: dict[str, dict[str, Any]] = {}
    for m in mapeados:
        por_chave[m["os_original"]] = m
    return list(por_chave.values())


def _is_aberta(status: str | None) -> bool:
    """OS aberta = status não começa com 'Fechada' e não é 'Cancelado'.

    Definido com o usuário (os valores reais não usam 'Encerrada').
    """
    if not status:
        return False
    return not status.startswith("Fechada") and status.strip().lower() != "cancelado"


def _sync_servicos_para_db(db: Session, servicos: list[dict[str, Any]]) -> dict[str, int]:
    """Faz upsert em ``solicitacao_servico`` e retorna contagens (inseridos/atualizados/ignorados)."""
    mapeados_brutos = [m for s in servicos if (m := _map_payload(s)) is not None]
    ignorados = len(servicos) - len(mapeados_brutos)
    mapeados = _deduplicar(mapeados_brutos)

    if not mapeados:
        return {"inseridos": 0, "atualizados": 0, "ignorados": ignorados}

    chaves = [m["os_original"] for m in mapeados]
    existentes = set(
        db.execute(
            select(SolicitacaoServico.os_original).where(
                SolicitacaoServico.os_original.in_(chaves)
            )
        ).scalars().all()
    )

    campos_atualizaveis = [
        k for k in mapeados[0] if k not in ("os_original", "criado_em")
    ]

    # PostgreSQL limita a ~65535 parâmetros por statement; quebra em lotes.
    tamanho_lote = 1000
    for inicio in range(0, len(mapeados), tamanho_lote):
        lote = mapeados[inicio : inicio + tamanho_lote]
        stmt = pg_insert(SolicitacaoServico).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SolicitacaoServico.os_original],
            set_={k: stmt.excluded[k] for k in campos_atualizaveis},
        )
        db.execute(stmt)
    db.commit()

    inseridos = len(set(chaves) - existentes)
    atualizados = len(set(chaves) & existentes)
    return {"inseridos": inseridos, "atualizados": atualizados, "ignorados": ignorados}


def sync_servicos(lookback_days: int | None = None) -> dict[str, int]:
    """Ponto de entrada do job: busca no Proxxima e grava no Postgres.

    Executa de forma síncrona (nunca dentro de um endpoint async).
    Inclui retry com backoff para lidar com instabilidade do servidor Aniel.
    """
    days = lookback_days if lookback_days is not None else settings.proxxima_lookback_days
    max_retries = 3
    retry_delay = 10

    for attempt in range(1, max_retries + 1):
        client = ProxximaClient(settings.proxxima_user, settings.proxxima_password)
        try:
            servicos = client.fetch_servicos(lookback_days=days)
            client.close()
            break
        except ProxximaRequestError as exc:
            client.close()
            if attempt < max_retries:
                logger.warning(
                    "[proxxima] Tentativa %d/%d falhou: %s. Retentando em %ds...",
                    attempt, max_retries, exc, retry_delay,
                )
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error(
                    "[proxxima] Todas as %d tentativas falharam: %s",
                    max_retries, exc,
                )
                raise

    db = SessionLocal()
    try:
        resultado = _sync_servicos_para_db(db, servicos)
    finally:
        db.close()

    logger.info(
        "[proxxima] %d serviços da API -> %s",
        len(servicos),
        resultado,
    )
    return resultado


_scheduler = None


def start_scheduler() -> None:
    """Agenda o sync periódico (padrão: a cada 30 min, mesmo do app local)."""
    global _scheduler
    if _scheduler is not None or not (settings.proxxima_user and settings.proxxima_password):
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler(timezone=str(TIMEZONE))
    _scheduler.add_job(
        sync_servicos,
        "interval",
        seconds=settings.proxxima_sync_interval_seconds,
        id="sync_proxxima",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "[proxxima] sync agendado a cada %d s (lookback %d dias)",
        settings.proxxima_sync_interval_seconds,
        settings.proxxima_lookback_days,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
