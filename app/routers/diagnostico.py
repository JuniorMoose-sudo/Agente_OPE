"""Endpoints de cruzamento (Sprint 4).

Async e somente leitura do Postgres já sincronizado — juntam as três fontes
(recorrência/Proxxima, painel-ope, inspeção) por técnico ou por unidade.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import exigir_token_ops
from app.models.ocorrencia_recorrencia import OcorrenciaRecorrencia
from app.models.solicitacao_servico import SolicitacaoServico
from app.schemas.diagnostico import (
    ComparativoUnidades,
    DiagnosticoTecnico,
    InspecaoResumo,
    StatusUnidade,
)
from app.services.cruzamento import (
    _calcular_alerta,
    buscar_banco_horas_tecnico,
    buscar_banco_horas_unidade,
    buscar_infracoes_unidade,
    buscar_metricas_recorrencia,
    buscar_produtividade,
    buscar_ultima_inspecao,
    normalizar_unidade,
)

router = APIRouter(
    prefix="/diagnostico",
    tags=["diagnostico"],
    dependencies=[Depends(exigir_token_ops)],
)


@router.get("/tecnico/{nome_tecnico}", response_model=DiagnosticoTecnico)
async def diagnostico_tecnico(
    nome_tecnico: str,
    periodo_de: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    periodo_ate: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> DiagnosticoTecnico:
    """Diagnóstico completo de um técnico: recorrência, produtividade, HE, infrações e inspeção."""
    rec_prod = buscar_metricas_recorrencia(db, nome_tecnico, periodo_de, periodo_ate)
    banco_horas = buscar_banco_horas_tecnico(db, nome_tecnico, periodo_de, periodo_ate)
    inspecao = buscar_ultima_inspecao(db, nome_tecnico)
    alerta = _calcular_alerta(rec_prod, banco_horas, inspecao)

    return DiagnosticoTecnico(
        tecnico=nome_tecnico,
        periodo_de=periodo_de,
        periodo_ate=periodo_ate,
        recorrencia_reaberturas=rec_prod["reabriu_total"],
        recorrencia_total_protocolos=rec_prod["total_protocolos"],
        produtividade=buscar_produtividade(db, nome_tecnico, periodo_de, periodo_ate),
        he_horas=banco_horas["he_horas"],
        infracoes=banco_horas["infracoes"],
        ultima_inspecao=(
            InspecaoResumo(
                data_inspecao=inspecao["data_inspecao"],
                pontuacao=inspecao["pontuacao"],
                inspetor=inspecao["inspetor"],
            )
            if inspecao
            else None
        ),
        alerta=alerta,
    )


def _status_unidade(db: Session, unidade: str, periodo_de: date, periodo_ate: date) -> StatusUnidade:
    """Agrega backlog (Proxxima) + HE/infrações (painel-ope) + recorrência de uma unidade."""
    unidade_normalizada = normalizar_unidade(unidade)

    # Backlog via solicitacao_servico (grupo_Area): estado atual, excluindo naturezas
    # de recolhimento (o painel-ope não as conta em "aberto agora").
    naturezas_excluídas = ("RECOLHIMENTO", "RECOLHIMENTO AGENDADO")
    abertas = db.scalar(
        select(func.count())
        .select_from(SolicitacaoServico)
        .where(
            (SolicitacaoServico.unidade.ilike(f"%{unidade_normalizada}%"))
            & (SolicitacaoServico.status.notilike("Fechada%"))
            & (SolicitacaoServico.status.ilike("Aberta%"))
            & (SolicitacaoServico.natureza.is_not(None))
            & (SolicitacaoServico.natureza.notin_(naturezas_excluídas))
            & (SolicitacaoServico.natureza != "")
        )
    ) or 0

    # Fechamentos e cancelamentos do período
    linhas = db.execute(
        select(SolicitacaoServico.status, func.count())
        .where(
            (SolicitacaoServico.unidade.ilike(f"%{unidade_normalizada}%"))
            & (SolicitacaoServico.abertura >= periodo_de)
            & (SolicitacaoServico.abertura <= periodo_ate)
            & (SolicitacaoServico.status.notilike("Aberta%"))
            & (SolicitacaoServico.status != "Cancelado")
        )
        .group_by(SolicitacaoServico.status)
    ).all()

    fech_prod = fech_improd = 0
    for status, count in linhas:
        if status and status.startswith("Fechada Produtiva"):
            fech_prod += count
        elif status and status.startswith("Fechada Improdutiva"):
            fech_improd += count

    canceladas = db.scalar(
        select(func.count())
        .select_from(SolicitacaoServico)
        .where(
            (SolicitacaoServico.unidade.ilike(f"%{unidade_normalizada}%"))
            & (SolicitacaoServico.abertura >= periodo_de)
            & (SolicitacaoServico.abertura <= periodo_ate)
            & (SolicitacaoServico.status == "Cancelado")
        )
    ) or 0

    # Recorrência via ocorrencia_recorrencia (unidade "UNIDADE X")
    recorrencias = db.scalar(
        select(func.count())
        .select_from(OcorrenciaRecorrencia)
        .where(
            (OcorrenciaRecorrencia.data_abertura >= periodo_de)
            & (OcorrenciaRecorrencia.data_abertura <= periodo_ate)
            & (OcorrenciaRecorrencia.e_recorrencia.is_(True))
            & (OcorrenciaRecorrencia.unidade.ilike(f"%{unidade_normalizada}%"))
        )
    ) or 0

    banco_horas = buscar_banco_horas_unidade(db, unidade_normalizada, periodo_de, periodo_ate)
    infr_dias = buscar_infracoes_unidade(db, unidade_normalizada, periodo_de, periodo_ate)

    return StatusUnidade(
        unidade=unidade_normalizada,
        abertas=abertas,
        fechadas_produtivas=fech_prod,
        fechadas_improdutivas=fech_improd,
        canceladas=canceladas,
        he_horas=banco_horas["he_horas"],
        infr_dias=infr_dias,
        recorrencias=recorrencias,
    )


@router.get("/status-unidade/{unidade}", response_model=StatusUnidade)
async def status_unidade(
    unidade: str,
    periodo_de: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    periodo_ate: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> StatusUnidade:
    """Status agregado de uma unidade: backlog + HE + recorrência."""
    return _status_unidade(db, unidade, periodo_de, periodo_ate)


@router.get("/comparativo-unidades", response_model=ComparativoUnidades)
async def comparativo_unidades(
    periodo_de: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    periodo_ate: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> ComparativoUnidades:
    """Comparativo lado a lado das duas unidades (Campina Grande vs Lagoa Seca)."""
    unidades = [
        _status_unidade(db, "REG-CAMPINA GRANDE", periodo_de, periodo_ate),
        _status_unidade(db, "REG-LAGOA SECA", periodo_de, periodo_ate),
    ]
    return ComparativoUnidades(periodo_de=periodo_de, periodo_ate=periodo_ate, unidades=unidades)
