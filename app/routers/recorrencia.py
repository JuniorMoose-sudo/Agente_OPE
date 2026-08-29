"""Endpoints de leitura de recorrência (Excel "Analítico" + join Proxxima).

Async e somente leitura do Postgres já sincronizado/importado — nunca chamam
API externa dentro do tempo de resposta.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.ocorrencia_recorrencia import OcorrenciaRecorrencia
from app.schemas.recorrencia import (
    ProblemaItem,
    RankingItem,
    RankingRecorrencia,
    RecorrenciaDetalhe,
    RecorrenciaPorProblema,
    RecorrenciaPorTecnico,
    ResumoCategoria,
)
from app.services.cruzamento import normalizar_unidade

router = APIRouter(prefix="/recorrencia", tags=["recorrencia"])


# ── Categorização da causa ("Problema do fechamento") em 3 grupos macro ──
# Heurística por palavra-chave, exportada para testes e ajustável contra o
# painel. Qualquer causa sem regra cai em culpa_do_campo (default).

MAPA_CATEGORIA_RECORRENCIA: dict[str, tuple[str, ...]] = {
    "administrativo": ("CLIENTE DESISTIU", "CLIENTE EM MASSIVA"),
    "rede_externa": ("ORIGEM REDES", "ORIGEM INFRA"),
}


def categorizar_problema(problema: str | None) -> str:
    """Devolve a categoria macro da causa de recorrência."""
    if not problema:
        return "sem_problema"
    texto = str(problema).upper()
    for categoria, chaves in MAPA_CATEGORIA_RECORRENCIA.items():
        if any(c in texto for c in chaves):
            return categoria
    return "culpa_do_campo"


def _ranking_recorrencia(
    db: Session, unidade: str, periodo_de: date, periodo_ate: date, top: int
) -> dict:
    """Técnicos com mais recorrências (é_recorrencia = SIM) de uma unidade.

    Uma consulta agrega por técnico: total de OS do técnico no analítico e
    quantas são recorrência. Exclui técnicos sem join (tecnico None) — o
    `total_recorrencias` da unidade compensa a contagem.
    """
    unidade_normalizada = normalizar_unidade(unidade)

    linhas = db.execute(
        select(
            OcorrenciaRecorrencia.tecnico,
            func.count().label("os_analitico"),
            func.sum(cast(OcorrenciaRecorrencia.e_recorrencia, Integer)).label("recorrencias"),
        )
        .where(
            OcorrenciaRecorrencia.tecnico.isnot(None),
            OcorrenciaRecorrencia.unidade.ilike(f"%{unidade_normalizada}%"),
            OcorrenciaRecorrencia.data_abertura >= periodo_de,
            OcorrenciaRecorrencia.data_abertura <= periodo_ate,
        )
        .group_by(OcorrenciaRecorrencia.tecnico)
        .order_by(func.sum(cast(OcorrenciaRecorrencia.e_recorrencia, Integer)).desc())
        .limit(top)
    ).all()

    ranking = []
    for tecnico, os_analitico, recorrencias in linhas[:top]:
        if not tecnico:
            continue
        ranking.append(
            RankingItem(
                tecnico=tecnico,
                recorrencias=int(recorrencias or 0),
                os_no_analitico=int(os_analitico or 0),
                taxa=round((int(recorrencias or 0) / int(os_analitico or 0)) * 100, 1)
                if int(os_analitico or 0) > 0
                else 0.0,
            )
        )

    total_recorrencias = (
        db.scalar(
            select(func.count())
            .select_from(OcorrenciaRecorrencia)
            .where(
                OcorrenciaRecorrencia.e_recorrencia.is_(True),
                OcorrenciaRecorrencia.unidade.ilike(f"%{unidade_normalizada}%"),
                OcorrenciaRecorrencia.data_abertura >= periodo_de,
                OcorrenciaRecorrencia.data_abertura <= periodo_ate,
            )
        )
        or 0
    )

    return {
        "unidade": unidade_normalizada,
        "periodo_de": periodo_de,
        "periodo_ate": periodo_ate,
        "top": top,
        "total_recorrencias": total_recorrencias,
        "ranking": ranking,
    }


def _por_problema(
    db: Session, unidade: str, periodo_de: date, periodo_ate: date
) -> dict:
    """Recorrências de uma unidade quebradas por causa + resumo em 3 categorias."""
    unidade_normalizada = normalizar_unidade(unidade)

    linhas = db.execute(
        select(OcorrenciaRecorrencia.problema_fechamento, func.count())
        .where(
            OcorrenciaRecorrencia.e_recorrencia.is_(True),
            OcorrenciaRecorrencia.unidade.ilike(f"%{unidade_normalizada}%"),
            OcorrenciaRecorrencia.data_abertura >= periodo_de,
            OcorrenciaRecorrencia.data_abertura <= periodo_ate,
        )
        .group_by(OcorrenciaRecorrencia.problema_fechamento)
        .order_by(func.count().desc())
    ).all()

    total = sum(int(n or 0) for _, n in linhas)
    por_problema: list[ProblemaItem] = []
    categorias: dict[str, int] = {}
    for problema, n in linhas:
        contagem = int(n or 0)
        rotulo = problema or "SEM PROBLEMA REGISTRADO"
        por_problema.append(
            ProblemaItem(
                problema=rotulo,
                recorrencias=contagem,
                pct=round((contagem / total) * 100, 1) if total else 0.0,
            )
        )
        categoria = categorizar_problema(problema)
        categorias[categoria] = categorias.get(categoria, 0) + contagem

    resumo = {
        categoria: ResumoCategoria(
            recorrencias=contagem,
            pct=round((contagem / total) * 100, 1) if total else 0.0,
        )
        for categoria, contagem in sorted(categorias.items())
    }

    return {
        "unidade": unidade_normalizada,
        "periodo_de": periodo_de,
        "periodo_ate": periodo_ate,
        "total_recorrencias": total,
        "por_problema": por_problema,
        "resumo_categorias": resumo,
    }


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


@router.get("/ranking", response_model=RankingRecorrencia)
async def ranking(
    unidade: str = Query(...),
    periodo_de: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    periodo_ate: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    top: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> RankingRecorrencia:
    """Ranking de técnicos com mais recorrências (é_recorrencia = SIM) da unidade no período."""
    return RankingRecorrencia(**_ranking_recorrencia(db, unidade, periodo_de, periodo_ate, top))


@router.get("/por-problema", response_model=RecorrenciaPorProblema)
async def por_problema(
    unidade: str = Query(...),
    periodo_de: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    periodo_ate: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> RecorrenciaPorProblema:
    """Recorrências da unidade no período quebradas por causa (Problema do fechamento)."""
    return RecorrenciaPorProblema(**_por_problema(db, unidade, periodo_de, periodo_ate))
