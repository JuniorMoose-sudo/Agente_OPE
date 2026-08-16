"""Endpoints de leitura de recorrência (Excel "Analítico" + join Proxxima).

Async e somente leitura do Postgres já sincronizado/importado — nunca chamam
API externa dentro do tempo de resposta.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.ocorrencia_recorrencia import OcorrenciaRecorrencia
from app.schemas.recorrencia import RecorrenciaDetalhe, RecorrenciaPorTecnico

router = APIRouter(prefix="/recorrencia", tags=["recorrencia"])


@router.get("/por-tecnico", response_model=RecorrenciaPorTecnico)
async def por_tecnico(
    tecnico: str,
    periodo_de: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    periodo_ate: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> RecorrenciaPorTecnico:
    """Protocolos de um técnico no período, com contagem de recorrências (é_recorrencia = SIM)."""
    filtro = (
        (OcorrenciaRecorrencia.tecnico == tecnico)
        & (OcorrenciaRecorrencia.data_abertura >= periodo_de)
        & (OcorrenciaRecorrencia.data_abertura <= periodo_ate)
    )

    total = db.scalar(select(func.count()).select_from(OcorrenciaRecorrencia).where(filtro)) or 0
    recorrencias = (
        db.scalar(
            select(func.count())
            .select_from(OcorrenciaRecorrencia)
            .where(filtro, OcorrenciaRecorrencia.e_recorrencia.is_(True))
        )
        or 0
    )

    return RecorrenciaPorTecnico(
        tecnico=tecnico,
        periodo_de=periodo_de,
        periodo_ate=periodo_ate,
        total_protocolos=total,
        recorrencias=recorrencias,
    )


@router.get("/detalhe", response_model=list[RecorrenciaDetalhe])
async def detalhe(
    tecnico: str,
    periodo_de: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    periodo_ate: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> list[RecorrenciaDetalhe]:
    """Detalhe dos protocolos de um técnico no período (útil para conferir com o painel)."""
    registros = db.scalars(
        select(OcorrenciaRecorrencia)
        .where(
            OcorrenciaRecorrencia.tecnico == tecnico,
            OcorrenciaRecorrencia.data_abertura >= periodo_de,
            OcorrenciaRecorrencia.data_abertura <= periodo_ate,
        )
        .order_by(OcorrenciaRecorrencia.data_abertura)
    ).all()

    return [
        RecorrenciaDetalhe(
            protocolo=r.protocolo,
            unidade=r.unidade,
            cidade=r.cidade,
            problema_fechamento=r.problema_fechamento,
            protocolo_anterior=r.protocolo_anterior,
            dias_entre_os=r.dias_entre_os,
            data_abertura=r.data_abertura,
            data_fechamento=r.data_fechamento,
        )
        for r in registros
    ]
