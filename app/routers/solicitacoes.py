"""Endpoints de leitura de solicitações (Proxxima).

Async e somente leitura do Postgres já sincronizado — nunca chamam a API
externa dentro do tempo de resposta.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.jobs.sync_proxxima import _is_aberta
from app.models.solicitacao_servico import SolicitacaoServico
from app.schemas.solicitacoes import (
    SolicitacaoDetalhe,
    SolicitacaoResumo,
    SolicitacoesPorTecnico,
)

router = APIRouter(prefix="/solicitacoes", tags=["solicitacoes"])


@router.get("/resumo", response_model=SolicitacaoResumo)
async def resumo(unidade: str, db: Session = Depends(get_db)) -> SolicitacaoResumo:
    """Resumo de solicitações por unidade (grupo_Area, ex.: REG-CAMPINA GRANDE)."""
    resultado = await _aggregate_by_status(db, SolicitacaoServico.unidade == unidade)
    return SolicitacaoResumo(unidade=unidade, **resultado)


@router.get("/por-tecnico", response_model=SolicitacoesPorTecnico)
async def por_tecnico(tecnico: str, db: Session = Depends(get_db)) -> SolicitacoesPorTecnico:
    """Solicitações de um técnico (nome completo em maiúsculas, como no painel)."""
    registros = db.scalars(
        select(SolicitacaoServico)
        .where(SolicitacaoServico.tecnico == tecnico)
        .order_by(SolicitacaoServico.abertura.desc())
    ).all()

    if not registros:
        return SolicitacoesPorTecnico(tecnico=tecnico, total=0, abertas=0, detalhe=[])

    detalhe = [
        SolicitacaoDetalhe(
            os=r.os,
            unidade=r.unidade,
            natureza=r.natureza,
            status=r.status,
            abertura=r.abertura,
            venc=r.venc,
            sla_status=r.sla_status,
        )
        for r in registros
    ]
    return SolicitacoesPorTecnico(
        tecnico=tecnico,
        total=len(registros),
        abertas=sum(1 for r in registros if _is_aberta(r.status)),
        detalhe=detalhe,
    )


async def _aggregate_by_status(db: Session, filtro) -> dict:
    """Agrega solicitações por categoria de status (definição de 'aberta' validada)."""
    linhas = db.execute(
        select(SolicitacaoServico.status, func.count())
        .where(filtro)
        .group_by(SolicitacaoServico.status)
    ).all()

    total = 0
    abertas = 0
    fechadas_produtivas = 0
    fechadas_improdutivas = 0
    canceladas = 0

    for status, count in linhas:
        total += count
        if _is_aberta(status):
            abertas += count
        elif status and status.strip().lower() == "cancelado":
            canceladas += count
        elif status and status.startswith("Fechada Produtiva"):
            fechadas_produtivas += count
        elif status and status.startswith("Fechada Improdutiva"):
            fechadas_improdutivas += count

    return {
        "total": total,
        "abertas": abertas,
        "fechadas_produtivas": fechadas_produtivas,
        "fechadas_improdutivas": fechadas_improdutivas,
        "canceladas": canceladas,
    }
