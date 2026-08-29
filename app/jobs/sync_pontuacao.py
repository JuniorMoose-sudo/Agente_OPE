"""Job de sincronização da pontuação das equipes (n8n aniel-aovivo).

Job síncrono agendado (APScheduler), fora do ciclo de request dos endpoints.
Baixa o payload ``aniel-aovivo`` e grava em ``pontuacao_tecnico_dia`` a soma
dos ``pontos`` dos fechamentos do dia (encDK) por técnico/unidade.

Frequência: a cada 1h (o webhook é atualizado pelo n8n durante o dia), com
primeira execução logo após o start. O webhook é público (sem auth) e o job é
somente leitura da fonte externa — escreve apenas no nosso Postgres.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.pontuacao_tecnico_dia import PontuacaoTecnicoDia
from app.services.aniel_client import AnielClient, AnielRequestError, sumarizar_pontuacao

logger = logging.getLogger(__name__)

INTERVALO_SEGUNDOS = 3600  # 1h
TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _nao_pontua_set(payload: dict[str, Any]) -> set[str]:
    """Conjunto de técnicos que não pontuam (lista do webhook, em minúsculas)."""
    return {
        str(nome).strip().upper()
        for nome in (payload.get("naoPontua") or [])
        if str(nome).strip()
    }


def _montar_linhas(payload: dict[str, Any], dias_olhar: set[str]) -> list[dict[str, Any]]:
    """Linhas de pontuação (tecnico, unidade, data, pontos, nao_pontua) do payload.

    Função pura (testável sem banco): soma os ``pontos`` por técnico/unidade/dia
    e filtra pelos dias da semana em ``dias_olhar`` (ex.: a semana atual), para
    não reimportar o histórico inteiro a cada rodada.
    """
    soma = sumarizar_pontuacao(payload.get("fechSemana") or [])
    nao_pontua = _nao_pontua_set(payload)

    linhas: list[dict[str, Any]] = []
    for (tecnico, unidade, dia), pontos in sorted(soma.items()):
        if dia not in dias_olhar:
            continue
        try:
            data = date.strptime(dia, "%Y%m%d")
        except ValueError:
            continue
        linhas.append(
            {
                "tecnico": tecnico,
                "unidade": unidade,
                "data": data,
                "pontos": round(pontos, 2),
                "nao_pontua": tecnico in nao_pontua,
            }
        )
    return linhas


def _sync_para_db(db: Session, payload: dict[str, Any], dias_olhar: set[str]) -> tuple[int, int]:
    """Grava as somas de pontuação do payload; retorna (gravados, fora_da_semana)."""
    soma = sumarizar_pontuacao(payload.get("fechSemana") or [])
    linhas = _montar_linhas(payload, dias_olhar)

    sem_dia = len(soma) - len(linhas)
    if linhas:
        colunas = [k for k in linhas[0]]
        stmt = pg_insert(PontuacaoTecnicoDia).values(linhas)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                PontuacaoTecnicoDia.tecnico,
                PontuacaoTecnicoDia.unidade,
                PontuacaoTecnicoDia.data,
            ],
            set_={
                "pontos": stmt.excluded.pontos,
                "nao_pontua": stmt.excluded.nao_pontua,
            },
        )
        db.execute(stmt)
        db.commit()
    return len(linhas), sem_dia


def _dias_da_semana(data_de: str, data_ate: str) -> set[str]:
    """Todos os YYYYMMDD de data_de..data_ate (inclusive)."""
    de = date.strptime(data_de, "%Y-%m-%d")
    ate = date.strptime(data_ate, "%Y-%m-%d")
    dias: set[str] = set()
    atual = de
    while atual <= ate:
        dias.add(atual.strftime("%Y%m%d"))
        atual = date.fromordinal(atual.toordinal() + 1)
    return dias


def _semana_atual_dk(referencia: date | None = None) -> tuple[str, str]:
    """Segunda e domingo da semana de ``referencia`` em YYYY-MM-DD.

    O dia "hoje" é sempre o dia atual no Brasil (America/Sao_Paulo), para não
    divergir do painel n8n quando o servidor está em UTC.
    """
    ref = referencia or datetime.now(TIMEZONE).date()
    segunda = ref - timedelta(days=ref.weekday())
    return segunda.isoformat(), (segunda + timedelta(days=6)).isoformat()


def sync_pontuacao() -> dict[str, Any]:
    """Ponto de entrada: baixa o aovivo e atualiza a pontuação da semana."""
    de, ate = _semana_atual_dk()
    dias = _dias_da_semana(de, ate)

    db = SessionLocal()
    try:
        with AnielClient() as client:
            payload = client.fetch_aovivo()
        gravados, sem_dia = _sync_para_db(db, payload, dias)
        resultado = {
            "semana_de": de,
            "semana_ate": ate,
            "gravados": gravados,
            "fora_da_semana": sem_dia,
            "gerado_em": payload.get("geradoEm"),
        }
    except AnielRequestError:
        logger.exception("[pontuacao] falha ao sincronizar webhook n8n")
        raise
    finally:
        db.close()

    logger.info("[pontuacao] %s", resultado)
    return resultado


_scheduler = None


def start_scheduler() -> None:
    """Agenda o sync da pontuação (a cada 1h, primeira execução imediata)."""
    global _scheduler
    if _scheduler is not None:
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        sync_pontuacao,
        "interval",
        seconds=INTERVALO_SEGUNDOS,
        id="sync_pontuacao",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    _scheduler.start()
    logger.info("[pontuacao] sync agendado a cada %d s", INTERVALO_SEGUNDOS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None