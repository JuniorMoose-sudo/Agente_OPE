"""Job de sincronização do painel-ope (banco de horas, HE e infrações).

Job síncrono agendado (APScheduler), fora do ciclo de request dos endpoints.
Sincroniza o setor REG02 (Campina Grande + Lagoa Seca — verificado com o
usuário; não há setor separado para Lagoa Seca no painel):

- ``/api/analises`` (janela semanal) -> snapshot em ``banco_horas_semanal``
  e linhas em ``infracao`` (``infracoesListaSemana``).
- ``/api/semanatec`` -> ``roster_tecnico`` (validador de nomes).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.jobs.checar_cookie import checar_expiracao_cookie
from app.models.banco_horas_semanal import BancoHorasSemanal
from app.models.infracao import Infracao
from app.models.roster_tecnico import RosterTecnico
from app.services.painel_ope_client import AuthenticationError, PainelOpeClient
from app.services.telegram import avisar_telegram

logger = logging.getLogger(__name__)

# Setores sincronizados: apenas REG02 (Campina Grande + Lagoa Seca).
SETORES = ("REG02",)

DATA_KEY_FORMAT = "%Y%m%d"


def _parse_data_key(value: Any) -> date | None:
    """Converte ``dataKey`` (YYYYMMDD) para date; retorna None se ausente."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), DATA_KEY_FORMAT).date()
    except ValueError:
        logger.warning("dataKey no formato inesperado: %r (registro gravado sem data)", value)
        return None


def _semana_atual(referencia: date | None = None) -> tuple[date, date]:
    """Segunda a domingo da semana de ``referencia`` (padrão: hoje)."""
    ref = referencia or date.today()
    segunda = ref - timedelta(days=ref.weekday())
    return segunda, segunda + timedelta(days=6)


def _chave_infracao(item: dict[str, Any]) -> tuple[str, str, str]:
    """Chave de unicidade para infração: (tecnico, dataKey, detalhe)."""
    tecnico = str(item.get("nome") or "")
    data_key = str(item.get("dataKey") or "")
    detalhe = str(item.get("detalhe") or "")
    return (tecnico, data_key, detalhe)


def _map_infracao(item: dict[str, Any], setor: str, semana_de: date, semana_ate: date) -> Infracao:
    return Infracao(
        setor=setor,
        semana_de=semana_de,
        semana_ate=semana_ate,
        tecnico=item.get("nome"),
        unidade=item.get("unidade"),
        sup=item.get("sup"),
        data=_parse_data_key(item.get("dataKey")),
        motivo=item.get("detalhe"),
        payload=item,
    )


def _sync_analises(db: Session, setor: str, de: date, ate: date) -> dict[str, int]:
    """Busca /analises, grava snapshot semanal e infrações. Retorna contagens."""
    with PainelOpeClient() as client:
        payload = client.get_analises(de=de.strftime("%Y%m%d"), ate=ate.strftime("%Y%m%d"), setor=setor)

    infracoes = payload.get("infracoesListaSemana") or []
    itens = [_map_infracao(item, setor, de, ate) for item in infracoes if isinstance(item, dict)]

    # Upsert do snapshot semanal (chave: setor + semana).
    stmt_snapshot = pg_insert(BancoHorasSemanal).values(
        setor=setor,
        semana_de=de,
        semana_ate=ate,
        payload=payload,
    )
    stmt_snapshot = stmt_snapshot.on_conflict_do_update(
        index_elements=[
            BancoHorasSemanal.setor,
            BancoHorasSemanal.semana_de,
            BancoHorasSemanal.semana_ate,
        ],
        set_={"payload": stmt_snapshot.excluded.payload},
    )
    db.execute(stmt_snapshot)

    # Upsert de infrações: sem ID próprio no payload, dedup por (tecnico, dataKey, detalhe).
    novos: list[Infracao] = []
    if itens:
        chaves_existentes = set(
            db.execute(
                select(Infracao.tecnico, Infracao.data, Infracao.motivo)
                .where(
                    Infracao.setor == setor,
                    Infracao.semana_de == de,
                    Infracao.semana_ate == ate,
                )
            ).all()
        )
        vistos = set()
        for item in itens:
            chave = (item.tecnico, item.data, item.motivo)
            if chave in chaves_existentes or chave in vistos:
                continue
            vistos.add(chave)
            novos.append(item)
        if novos:
            db.add_all(novos)

    db.commit()

    return {
        "infracoes": len(itens),
        "infracoes_novas": len(novos) if itens else 0,
        "he_horas": payload.get("totais", {}).get("heHoras"),
    }


def _sync_roster(db: Session, setor: str) -> int:
    """Busca /semanatec e atualiza o roster de técnicos do setor."""
    with PainelOpeClient() as client:
        payload = client.get_semanatec(setor=setor)

    tecnicos = payload.get("tecnicos") or []
    hoje = date.today()
    n = 0
    for nome in tecnicos:
        if not isinstance(nome, str) or not nome.strip():
            continue
        db.execute(
            pg_insert(RosterTecnico).values(tecnico=nome, setor=setor, ultimo_visto=hoje)
            .on_conflict_do_update(
                index_elements=[RosterTecnico.tecnico],
                set_={"setor": setor, "ultimo_visto": hoje},
            )
        )
        n += 1
    db.commit()
    return n


def sync_painel_ope() -> dict[str, Any]:
    """Ponto de entrada do job: sincroniza REG02 (semana atual)."""
    de, ate = _semana_atual()
    db = SessionLocal()
    try:
        resultado: dict[str, Any] = {"semana_de": de.isoformat(), "semana_ate": ate.isoformat()}
        for setor in SETORES:
            analises = _sync_analises(db, setor, de, ate)
            roster = _sync_roster(db, setor)
            resultado[setor] = {**analises, "roster": roster}
    except AuthenticationError as exc:
        avisar_telegram("⚠️ Falha de autenticação no painel-ope. Renove o cookie em painel-ope.vercel.app.")
        raise
    finally:
        db.close()

    logger.info("[painel-ope] %s", resultado)
    return resultado


_scheduler = None


def start_scheduler() -> None:
    """Agenda o sync do painel-ope (diário, cookie expira em ~7 dias)."""
    global _scheduler
    if _scheduler is not None or not settings.ope_session_cookie:
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        sync_painel_ope,
        "interval",
        days=1,
        id="sync_painel_ope",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        checar_expiracao_cookie,
        "interval",
        days=1,
        id="checar_cookie_ope",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("[painel-ope] sync diário agendado (setores: %s)", ", ".join(SETORES))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
