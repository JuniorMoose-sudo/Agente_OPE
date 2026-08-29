"""Job de sincronização da recorrência pelo painel Operações.

Baixa o analítico (xlsx) de ``operacoes.proxxima.net`` para Campina Grande e
Lagoa Seca (mês corrente) e importa via ``importar_recorrencia`` — o **mesmo
parser** do export manual (aba ``Analitico``). Substitui o passo manual de
exportação: recorrência fica visível para o agente sem depender de planilha.

Falha de autenticação (cookie expirado) dispara alerta no Telegram, no padrão
do painel-ope: alertar e falhar de forma controlada — nunca contorna auth.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.db import SessionLocal
from app.etl.recorrencia import importar_recorrencia
from app.services.operacoes_client import (
    OperacoesAuthError,
    OperacoesClient,
    OperacoesRequestError,
    UNIDADES_RECORRENCIA,
)
from app.services.telegram import avisar_telegram

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("America/Sao_Paulo")

# Horário do sync (UTC-3): manhã, depois do reprocessamento do GetAll.
SYNC_HORA = 6
SYNC_MINUTO = 15

PREFIXO_ARQUIVO = "recorrencia_painel_"


def _mes_atual() -> str:
    """Mês corrente em formato ``YYYY-MM`` (UTC-3)."""
    return datetime.now(TIMEZONE).strftime("%Y-%m")


def _baixar_analitico(client: OperacoesClient, unidade: str, mes: str) -> str:
    """Baixa o xlsx para arquivo temporário e devolve o caminho.

    Quem chama é responsável por remover o arquivo (try/finally).
    """
    conteudo = client.fetch_analitico(unidade, mes)
    fd, caminho = tempfile.mkstemp(prefix=PREFIXO_ARQUIVO, suffix=".xlsx")
    with os.fdopen(fd, "wb") as f:
        f.write(conteudo)
    return caminho


def sync_recorrencia_painel(mes: str | None = None) -> dict[str, dict[str, int]]:
    """Baixa o analítico das unidades no mês e importa em ``ocorrencia_recorrencia``.

    Retorna contagens por unidade para log. Levanta ``OperacoesAuthError`` (com
    alerta no Telegram) se o cookie expirar; demais falhas sobem como erro.
    """
    mes = mes or _mes_atual()
    resultados: dict[str, dict[str, int]] = {}

    client = OperacoesClient()
    db = SessionLocal()
    try:
        for unidade in UNIDADES_RECORRENCIA:
            caminho = _baixar_analitico(client, unidade, mes)
            try:
                contagens = importar_recorrencia(caminho, db)
            finally:
                os.unlink(caminho)
            resultados.setdefault(unidade, {})
            resultados[unidade] = contagens
            logger.info(
                "[recorrencia_painel] %s/%s -> %s",
                unidade,
                mes,
                contagens,
            )
    except OperacoesAuthError as exc:
        try:
            avisar_telegram(
                "⚠️ Cookie do painel Operações (operacoes.proxxima.net) expirou. "
                "Renove o OPERACOES_SESSION_COOKIE no .env para o sync de recorrência seguir."
            )
        finally:
            raise exc
    except OperacoesRequestError:
        logger.exception("[recorrencia_painel] falha de comunicação ao baixar analítico")
        raise
    finally:
        client.close()
        db.close()

    return resultados


_scheduler = None


def start_scheduler() -> None:
    """Agenda o sync diário do analítico (padrão: 06:15 UTC-3)."""
    global _scheduler
    if _scheduler is not None or not settings.operacoes_session_cookie:
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler(timezone=str(TIMEZONE))
    _scheduler.add_job(
        sync_recorrencia_painel,
        "cron",
        hour=SYNC_HORA,
        minute=SYNC_MINUTO,
        id="sync_recorrencia_painel",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "[recorrencia_painel] sync agendado diariamente às %02d:%02d (UTC-3)",
        SYNC_HORA,
        SYNC_MINUTO,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None