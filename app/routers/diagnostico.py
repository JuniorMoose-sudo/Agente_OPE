"""Endpoints de cruzamento (Sprint 4).

Async e somente leitura do Postgres já sincronizado — juntam as três fontes
(recorrência/Proxxima, painel-ope, inspeção) por técnico ou por unidade.
"""

from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo as TimeZone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.security import exigir_token_ops
from app.models.ocorrencia_recorrencia import OcorrenciaRecorrencia
from app.models.pontuacao_tecnico_dia import PontuacaoTecnicoDia
from app.models.solicitacao_servico import SolicitacaoServico
from app.schemas.diagnostico import (
    AgendadoNatureza,
    AgendadosResumo,
    ComparativoUnidades,
    DiagnosticoTecnico,
    InspecaoResumo,
    PontuacaoEquipe,
    PontuacaoEquipeResumo,
    PontuacaoTecnicoDiaResumo,
    PontuacaoTotvsResumo,
    StatusUnidade,
)
from app.services.cruzamento import (
    _calcular_alerta,
    buscar_banco_horas_tecnico,
    buscar_banco_horas_unidade,
    buscar_infracoes_unidade,
    buscar_metricas_recorrencia,
    buscar_pontuacao_totvs,
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
    pont_totvs = buscar_pontuacao_totvs(db, nome_tecnico, periodo_de, periodo_ate)
    alerta = _calcular_alerta(rec_prod, banco_horas, inspecao)

    return DiagnosticoTecnico(
        tecnico=nome_tecnico,
        periodo_de=periodo_de,
        periodo_ate=periodo_ate,
        recorrencia_reaberturas=rec_prod["reabriu_total"],
        recorrencia_os_no_analitico=rec_prod["total_protocolos"],
        recorrencia_contexto=(
            f"No analítico do período constam {rec_prod['total_protocolos']} OS deste técnico; "
            f"destas, {rec_prod['reabriu_total']} são recorrência (é_recorrencia=SIM). "
            f"Recorrência NÃO é concentrada em um único técnico da unidade."
        ),
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
        pontuacao_totvs=(
            PontuacaoTotvsResumo(**pont_totvs)
            if pont_totvs
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


_MAPA_UNIDADE = {
    "CAMPINA GRANDE": "CAMPINA GRANDE",
    "LAGOA SECA": "LAGOA SECA",
}


def _buscar_dados_tempo_real(unidade: str) -> dict:
    """Consulta a API Proxxima em tempo real e retorna dados agregados.

    Não salva no banco — é somente leitura para consulta imediata.
    """
    from app.services.proxxima_client import ProxximaClient, ProxximaRequestError

    unidade_upper = unidade.upper().strip()
    unidade_match = _MAPA_UNIDADE.get(unidade_upper)
    if not unidade_match:
        raise ValueError(f"Unidade inválida: {unidade}. Use CAMPINA GRANDE ou LAGOA SECA.")

    try:
        client = ProxximaClient(settings.proxxima_user, settings.proxxima_password)
        servicos = client.fetch_servicos(lookback_days=7)
        client.close()
    except ProxximaRequestError as exc:
        raise RuntimeError(f"Falha ao consultar Proxxima: {exc}") from exc

    dados = [s for s in servicos if unidade_match in (s.get("grupo_Area") or "").upper()]

    hoje_str = datetime.now().strftime("%d/%m/%Y")
    ontem = datetime.now() - timedelta(days=1)
    ontem_str = ontem.strftime("%d/%m/%Y")

    abertas = [
        s
        for s in dados
        if not (s.get("status_Execucao") or "").startswith("Fechada")
        and (s.get("status_Execucao") or "").lower() != "cancelado"
    ]

    status_count = Counter(s.get("status_Execucao", "N/A") for s in abertas)
    nat_abertas = Counter((s.get("natureza") or "N/A") for s in abertas)

    enc_ontem = [s for s in dados if (s.get("dataHora_Encerramento_OS") or "").startswith(ontem_str)]
    fp_ontem = len([s for s in enc_ontem if (s.get("status_Execucao") or "").startswith("Fechada Produtiva")])
    fi_ontem = len([s for s in enc_ontem if (s.get("status_Execucao") or "").startswith("Fechada Improdutiva")])

    abert_hoje = [s for s in dados if (s.get("dataHora_Abertura_OS") or "").startswith(hoje_str)]
    nat_hoje = Counter((s.get("natureza") or "N/A") for s in abert_hoje)

    enc_hoje = [s for s in dados if (s.get("dataHora_Encerramento_OS") or "").startswith(hoje_str)]
    fp_hoje = [s for s in enc_hoje if (s.get("status_Execucao") or "").startswith("Fechada Produtiva")]
    fi_hoje = [s for s in enc_hoje if (s.get("status_Execucao") or "").startswith("Fechada Improdutiva")]
    nat_fp_hoje = Counter((s.get("natureza") or "N/A") for s in fp_hoje)
    nat_fi_hoje = Counter((s.get("natureza") or "N/A") for s in fi_hoje)

    sla_vencido = len([
        s for s in abertas
        if "vencido" in (s.get("sla") or "").lower()
        or "Vencido" in (s.get("sla") or "")
    ])
    sem_tecnico = len([s for s in abertas if not s.get("responsavel")])

    return {
        "unidade": unidade_match,
        "fonte": "Proxxima API (tempo real)",
        "timestamp": datetime.now().isoformat(),
        "abertas_agora": len(abertas),
        "abertas_agora_por_natureza": dict(nat_abertas.most_common()),
        "detalhe_status": dict(status_count.most_common()),
        "encerradas_ontem": {
            "total": len(enc_ontem),
            "produtivas": fp_ontem,
            "improdutivas": fi_ontem,
        },
        "encerradas_hoje": {
            "total": len(enc_hoje),
            "produtivas": len(fp_hoje),
            "improdutivas": len(fi_hoje),
            "produtivas_por_natureza": dict(nat_fp_hoje.most_common()),
            "improdutivas_por_natureza": dict(nat_fi_hoje.most_common()),
        },
        "abertas_hoje": {
            "total": len(abert_hoje),
            "por_natureza": dict(nat_hoje.most_common()),
        },
        "sla_vencido": sla_vencido,
        "sem_tecnico": sem_tecnico,
    }


@router.get("/tempo-real/{unidade}")
async def tempo_real(unidade: str):
    """Dados em tempo real direto da API Proxxima — não usa banco de dados.

    Use quando precisar do estado atualizado das OS (panorama do dia, etc.).
    """
    return _buscar_dados_tempo_real(unidade)


def _tem_equipe(servico: SolicitacaoServico) -> bool:
    """OS já tem equipe = técnico responsável OU matrícula de equipe atribuída."""
    if servico.tecnico and str(servico.tecnico).strip():
        return True
    payload = servico.payload or {}
    return bool(str(payload.get("equipe_Matricula") or "").strip())


def _agendados_por_dia(db: Session, unidade: str, dia: date) -> AgendadosResumo:
    """Agrega os atendimentos agendados (data_Hora_Agendamento_OS) de um dia."""
    unidade_normalizada = normalizar_unidade(unidade)

    linhas = db.scalars(
        select(SolicitacaoServico)
        .where(
            (SolicitacaoServico.unidade.ilike(f"%{unidade_normalizada}%"))
            & (func.timezone("America/Sao_Paulo", SolicitacaoServico.agendamento).cast(Date) == dia)
            & (SolicitacaoServico.status.notilike("Fechada%"))
            & (SolicitacaoServico.status.is_not(None))
            & (SolicitacaoServico.status != "Cancelado")
        )
    ).all()

    por_natureza: dict[str, dict[str, int]] = {}
    com_equipe = 0
    for servico in linhas:
        natureza = servico.natureza or "SEM NATUREZA"
        item = por_natureza.setdefault(natureza, {"total": 0, "com_equipe": 0})
        item["total"] += 1
        if _tem_equipe(servico):
            com_equipe += 1
            item["com_equipe"] += 1

    lista = sorted(
        (
            AgendadoNatureza(
                natureza=natureza,
                total=item["total"],
                com_equipe=item["com_equipe"],
            )
            for natureza, item in por_natureza.items()
        ),
        key=lambda ag: (-ag.total, str(ag.natureza)),
    )

    return AgendadosResumo(
        unidade=unidade_normalizada,
        data=dia,
        total=len(linhas),
        com_equipe=com_equipe,
        sem_equipe=len(linhas) - com_equipe,
        por_natureza=list(lista),
    )


@router.get("/agendados/{unidade}", response_model=AgendadosResumo)
async def atendimentos_agendados(
    unidade: str,
    data: date = Query(..., description="Data dos agendamentos (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> AgendadosResumo:
    """Atendimentos agendados para uma data, por unidade e natureza.

    Fonte: ``data_Hora_Agendamento_OS`` do GetAll (Proxxima), já gravado na
    coluna ``agendamento`` de ``solicitacao_servico``. Inclui apenas OS ainda
    abertas (não fechadas/canceladas).
    """
    return _agendados_por_dia(db, unidade, data)


META_PONTOS_DIA = 8.0
META_PONTOS_SEMANA = 40.0


def _meta_dia(data: date) -> float | None:
    """Meta diária: 8 pontos de SEG a SEX; sábado/domingo não têm meta."""
    return META_PONTOS_DIA if data.weekday() < 5 else None


def _semana_do_dia(data: date) -> tuple[date, date]:
    """Segunda e domingo da semana (SEG a DOM) que contém ``data``."""
    segunda = data - timedelta(days=data.weekday())
    return segunda, segunda + timedelta(days=6)


def _agregar_pontuacao(db: Session, unidade: str, dia: date) -> PontuacaoEquipeResumo:
    """Pontuação das equipes no dia e na semana, com metas (8/dia útil, 40/semana)."""
    unidade_normalizada = normalizar_unidade(unidade)
    semana_de, semana_ate = _semana_do_dia(dia)
    meta_dia = _meta_dia(dia)

    linhas = db.scalars(
        select(PontuacaoTecnicoDia)
        .where(
            (PontuacaoTecnicoDia.unidade.ilike(f"%{unidade_normalizada}%"))
            & (PontuacaoTecnicoDia.data >= semana_de)
            & (PontuacaoTecnicoDia.data <= semana_ate)
        )
        .order_by(PontuacaoTecnicoDia.tecnico, PontuacaoTecnicoDia.data)
    ).all()

    por_tecnico: dict[str, dict] = {}
    for linha in linhas:
        tech = por_tecnico.setdefault(
            linha.tecnico,
            {
                "nao_pontua": linha.nao_pontua,
                "dias": [],
                "ponto_semana": 0.0,
                "pontos_dia": 0.0,
            },
        )
        pontos = float(linha.pontos or 0)
        pontos = round(pontos, 2)
        tech["dias"].append(
            PontuacaoTecnicoDiaResumo(
                data=linha.data,
                pontos=pontos,
                nao_pontua=linha.nao_pontua,
            )
        )
        tech["ponto_semana"] = round(tech["ponto_semana"] + pontos, 2)
        if linha.data == dia:
            tech["pontos_dia"] = pontos

    equipes = [
        PontuacaoEquipe(
            tecnico=tecnico,
            nao_pontua=info["nao_pontua"],
            pontos_dia=info["pontos_dia"],
            meta_dia=meta_dia,
            cumpre_meta_dia=(info["pontos_dia"] >= meta_dia) if meta_dia is not None else None,
            ponto_semana=info["ponto_semana"],
            meta_semana=META_PONTOS_SEMANA,
            cumpre_meta_semana=info["ponto_semana"] >= META_PONTOS_SEMANA,
            dias=info["dias"],
        )
        for tecnico, info in por_tecnico.items()
    ]
    equipes.sort(key=lambda eq: (-eq.ponto_semana, eq.tecnico))

    return PontuacaoEquipeResumo(
        unidade=unidade_normalizada,
        data=dia,
        fonte="n8n aniel-aovivo (fechSemana) — sincronizado",
        semana_de=semana_de,
        semana_ate=semana_ate,
        meta_dia=meta_dia,
        meta_semana=META_PONTOS_SEMANA,
        total_pontos_dia=round(sum(eq.pontos_dia for eq in equipes), 2),
        total_pontos_semana=round(sum(eq.ponto_semana for eq in equipes), 2) if equipes else 0.0,
        equipes=equipes,
    )


@router.get("/pontuacao/{unidade}", response_model=PontuacaoEquipeResumo)
async def pontuacao_equipes(
    unidade: str,
    data: date | None = Query(default=None, description="Data de referência (YYYY-MM-DD, padrão: hoje)"),
    db: Session = Depends(get_db),
) -> PontuacaoEquipeResumo:
    """Pontuação das equipes/técnicos da unidade no dia e na semana.

    Fonte: webhook n8n ``aniel-aovivo`` sincronizado em ``pontuacao_tecnico_dia``.
    A pontuação do dia da equipe é a soma dos ``pontos`` dos fechamentos do dia.
    Metas: 8 pontos/dia de SEG a SEX (sábado/domingo sem meta); 40 pontos na
    semana completa (SEG a DOM).
    """
    dia = data or datetime.now(TimeZone("America/Sao_Paulo")).date()
    return _agregar_pontuacao(db, unidade, dia)
