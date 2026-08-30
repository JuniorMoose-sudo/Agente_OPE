"""Cruzamento das três fontes por técnico ou unidade.

Leitura apenas do Postgres já sincronizado (nunca chama API externa):
- recorrência + produtividade: `ocorrencia_recorrencia` e `solicitacao_servico`
- banco de horas/HE: planilha pública (`banco_horas_saldo`, saldo por técnico/dia)
  — substitui o painel-ope como fonte (2026-08-30)
- infrações: snapshots `banco_horas_semanal` + tabela `infracao` (painel-ope)
- inspeção: `inspecao`

Chave de técnico e unidade: nome completo em maiúsculas / nome de unidade
normalizado (sem prefixo REG-/UNIDADE e sem sufixo de cidade), mesmo padrão
das fontes.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.banco_horas_saldo import BancoHorasSaldo
from app.models.banco_horas_semanal import BancoHorasSemanal
from app.models.infracao import Infracao
from app.models.inspecao import Inspecao
from app.models.metrica_totvs import MetricaTotvs
from app.models.ocorrencia_recorrencia import OcorrenciaRecorrencia
from app.models.solicitacao_servico import SolicitacaoServico
from app.jobs.sync_proxxima import _is_aberta
from app.services.totvs_client import REPORT_PONTUACAO_DIA_TECNICO, TotvsClient

# Limites de alerta — calibrados com o usuário em 2026-08-15.
# LIMITE_REABERTURA = 1: qualquer reabertura em menos de 30 dias para o
#   mesmo cliente já é crítico (definição de negócio, não limiar estatístico).
# LIMITE_BANCO_HORAS = 8.0: confirmado como adequado pelo usuário; a partir de
#   2026-08-30 vale para o SALDO do banco (planilha pública), que substitui o
#   HE do painel-ope (saldo positivo acima do limite = banco acumulado elevado).
# META_INSPECAO = 7.0: escala 0-10, confirmada pelo usuário.
LIMITE_REABERTURA = 1  # recorrências (SIM) por técnico no período
LIMITE_BANCO_HORAS = 8.0  # saldo de banco de horas (limite antes usado p/ HE)
META_INSPECAO = 7.0  # pontuação mínima de inspeção

_PREFIXOS_UNIDADE = ("REG-", "UNIDADE ")


def normalizar_unidade(valor: str | None) -> str:
    """Normaliza nome de unidade das 3 fontes para uma chave comum.

    'REG-CAMPINA GRANDE', 'UNIDADE CAMPINA GRANDE', 'CAMPINA GRANDE | PB'
    -> 'CAMPINA GRANDE'.
    """
    if not valor:
        return ""
    texto = str(valor).strip()
    for prefixo in _PREFIXOS_UNIDADE:
        if texto.upper().startswith(prefixo):
            texto = texto[len(prefixo) :]
    if " | " in texto:
        texto = texto.split(" | ", 1)[0]
    return texto.strip().upper()


def buscar_metricas_recorrencia(
    db: Session, tecnico: str, periodo_de: date, periodo_ate: date
) -> dict:
    """Protocolos de recorrência do técnico no período (abertura)."""
    filtro = (
        (OcorrenciaRecorrencia.tecnico == tecnico)
        & (OcorrenciaRecorrencia.data_abertura >= periodo_de)
        & (OcorrenciaRecorrencia.data_abertura <= periodo_ate)
    )
    total = db.scalar(select(func.count()).select_from(OcorrenciaRecorrencia).where(filtro)) or 0
    reabriu = (
        db.scalar(
            select(func.count())
            .select_from(OcorrenciaRecorrencia)
            .where(filtro, OcorrenciaRecorrencia.e_recorrencia.is_(True))
        )
        or 0
    )
    return {"total_protocolos": total, "reabriu_total": reabriu}


def buscar_produtividade(
    db: Session, tecnico: str, periodo_de: date, periodo_ate: date
) -> dict:
    """OS fechadas produtivas/improdutivas e abertas no período (por abertura)."""
    filtro = (
        (SolicitacaoServico.tecnico == tecnico)
        & (SolicitacaoServico.abertura >= periodo_de)
        & (SolicitacaoServico.abertura <= periodo_ate)
    )
    linhas = db.execute(
        select(SolicitacaoServico.status, func.count()).where(filtro).group_by(SolicitacaoServico.status)
    ).all()

    abertas = fech_prod = fech_improd = canceladas = 0
    for status, count in linhas:
        if _is_aberta(status):
            abertas += count
        elif status and status.startswith("Fechada Produtiva"):
            fech_prod += count
        elif status and status.startswith("Fechada Improdutiva"):
            fech_improd += count
        elif status and status.strip().lower() == "cancelado":
            canceladas += count

    return {
        "abertas": abertas,
        "fech_prod_total": fech_prod,
        "fech_improd_total": fech_improd,
        "canceladas": canceladas,
    }


def _snapshots_no_periodo(db: Session, periodo_de: date, periodo_ate: date) -> list[BancoHorasSemanal]:
    """Snapshots semanais que intersectam o período (por setor REG02)."""
    return list(
        db.scalars(
            select(BancoHorasSemanal)
            .where(BancoHorasSemanal.semana_ate >= periodo_de, BancoHorasSemanal.semana_de <= periodo_ate)
            .order_by(BancoHorasSemanal.semana_de)
        ).all()
    )


def buscar_ultimos_saldos(
    db: Session,
    periodo_de: date,
    periodo_ate: date,
    unidade: str | None = None,
) -> list[BancoHorasSaldo]:
    """Último saldo de banco de horas de cada técnico no período.

    Um registro por técnico (a data mais recente dentro do período). Se
    `unidade` for informada, filtra a unidade. Portável (subquery GROUP BY
    MAX), evita DISTINCT ON que só existe no Postgres.
    """
    filtros = [
        BancoHorasSaldo.data >= periodo_de,
        BancoHorasSaldo.data <= periodo_ate,
    ]
    if unidade:
        filtros.append(BancoHorasSaldo.unidade == unidade)

    max_data = (
        select(BancoHorasSaldo.tecnico, func.max(BancoHorasSaldo.data).label("ultima_data"))
        .where(*filtros)
        .group_by(BancoHorasSaldo.tecnico)
        .subquery()
    )
    return list(
        db.scalars(
            select(BancoHorasSaldo)
            .join(
                max_data,
                (BancoHorasSaldo.tecnico == max_data.c.tecnico)
                & (BancoHorasSaldo.data == max_data.c.ultima_data),
            )
            .order_by(BancoHorasSaldo.tecnico)
        ).all()
    )


def _ultimos_saldos(db: Session, unidade: str, periodo_de: date, periodo_ate: date) -> list[BancoHorasSaldo]:
    return buscar_ultimos_saldos(db, periodo_de, periodo_ate, unidade=unidade)


def buscar_saldo_banco_unidade(
    db: Session, unidade: str, periodo_de: date, periodo_ate: date
) -> dict:
    """Saldo de banco de horas resumido de uma unidade (último saldo por técnico)."""
    registros = _ultimos_saldos(db, unidade, periodo_de, periodo_ate)
    total = 0.0
    tecnicos = []
    for reg in registros:
        saldo = round(float(reg.saldo), 2) if reg.saldo is not None else None
        if saldo is not None:
            total += saldo
        tecnicos.append(
            {
                "tecnico": reg.tecnico,
                "unidade": reg.unidade,
                "data": reg.data.date() if reg.data else None,
                "saldo": saldo,
                "status": reg.status,
            }
        )
    return {"total_saldo": round(total, 2), "tecnicos": tecnicos}


def buscar_banco_horas_tecnico(
    db: Session, tecnico: str, periodo_de: date, periodo_ate: date
) -> dict:
    """Saldo de banco de horas e infrações de um técnico no período.

    Saldo: último registro da planilha pública (`banco_horas_saldo`) no período
    — substitui o HE do painel-ope (decisão 2026-08-30). Infrações: snapshots
    semanais do painel-ope, que permanece como fonte só de infrações.
    """
    reg = db.scalars(
        select(BancoHorasSaldo)
        .where(
            BancoHorasSaldo.tecnico == tecnico,
            BancoHorasSaldo.data >= periodo_de,
            BancoHorasSaldo.data <= periodo_ate,
        )
        .order_by(BancoHorasSaldo.data.desc())
        .limit(1)
    ).first()
    saldo = round(float(reg.saldo), 2) if reg and reg.saldo is not None else None
    dias_com_saldo = (
        db.scalar(
            select(func.count())
            .select_from(BancoHorasSaldo)
            .where(
                BancoHorasSaldo.tecnico == tecnico,
                BancoHorasSaldo.data >= periodo_de,
                BancoHorasSaldo.data <= periodo_ate,
            )
        )
        or 0
    )

    dias_infr = 0
    for snap in _snapshots_no_periodo(db, periodo_de, periodo_ate):
        payload = snap.payload or {}
        # infrDias é por unidade; somar apenas se o item for do técnico
        for item in payload.get("infracoesListaSemana") or []:
            if isinstance(item, dict) and item.get("nome") == tecnico:
                dias_infr += 1

    return {"saldo": saldo, "dias_com_saldo": dias_com_saldo, "infracoes": dias_infr}


def buscar_banco_horas_unidade(
    db: Session, unidade: str, periodo_de: date, periodo_ate: date
) -> dict:
    """Saldo de banco de horas agregado de uma unidade + infrações do painel-ope."""
    resumo = buscar_saldo_banco_unidade(db, unidade, periodo_de, periodo_ate)

    infr_dias = 0
    for snap in _snapshots_no_periodo(db, periodo_de, periodo_ate):
        payload = snap.payload or {}
        for item in payload.get("cardsUnidadeHE") or []:
            if isinstance(item, dict) and normalizar_unidade(item.get("chave")) == unidade:
                infr_dias += int(item.get("infrDias") or 0)

    return {
        "saldo": resumo["total_saldo"],
        "tecnicos_com_saldo": len(resumo["tecnicos"]),
        "infr_dias": infr_dias,
    }


def buscar_infracoes_unidade(db: Session, unidade: str, periodo_de: date, periodo_ate: date) -> int:
    """Contagem de infrações de uma unidade normalizada no período (tabela infracao)."""
    filtro = (
        (Infracao.unidade.isnot(None))
        & (Infracao.data >= periodo_de)
        & (Infracao.data <= periodo_ate)
    )
    linhas = db.execute(
        select(Infracao.unidade, func.count()).where(filtro).group_by(Infracao.unidade)
    ).all()
    return sum(count for u, count in linhas if normalizar_unidade(u) == unidade)


def buscar_ultima_inspecao(db: Session, tecnico: str) -> dict | None:
    """Última inspeção do técnico (None se não houver)."""
    reg = db.scalars(
        select(Inspecao)
        .where(Inspecao.tecnico == tecnico)
        .order_by(Inspecao.data_inspecao.desc())
    ).first()
    if not reg:
        return None
    return {
        "data_inspecao": reg.data_inspecao,
        "pontuacao": float(reg.pontuacao) if reg.pontuacao is not None else None,
        "inspetor": reg.inspetor,
    }


def buscar_pontuacao_totvs(
    db: Session, tecnico: str, periodo_de: date, periodo_ate: date
) -> dict | None:
    """Pontuação TOTVS (GoodData) do técnico no período.

    Busca o snapshot mais recente da tabela ``metrica_totvs`` (report 2837323),
    parseia o ``xtab_data`` hierárquico e filtra por técnico + período.

    Retorna dict com:
    - ``pontuacao_media``: média das pontuações no período
    - ``pontuacao_total``: soma das pontuações no período
    - ``dias_com_dados``: quantos dias o técnico aparece
    - ``detalhes``: lista de ``{"data": ..., "pontuacao": ...}`` (últimos 10)
    ou ``None`` se não houver dados.
    """
    from datetime import datetime as _dt

    reg = db.scalars(
        select(MetricaTotvs)
        .where(MetricaTotvs.report_id == REPORT_PONTUACAO_DIA_TECNICO)
        .order_by(MetricaTotvs.data_referencia.desc())
        .limit(1)
    ).first()
    if not reg or not reg.payload:
        return None

    xtab = reg.payload.get("xtab_data", reg.payload)
    dados = TotvsClient.parse_xtab_data(xtab)

    registros = []
    for r in dados:
        if r.get("tecnico") != tecnico:
            continue
        try:
            data_ref = _dt.strptime(r["data"], "%d/%m/%Y").date()
        except (ValueError, KeyError):
            continue
        if data_ref < periodo_de or data_ref > periodo_ate:
            continue
        try:
            pontuacao = float(r.get("pontuacao", 0))
        except (ValueError, TypeError):
            pontuacao = 0.0
        registros.append({"data": data_ref, "pontuacao": pontuacao})

    if not registros:
        return None

    total = sum(r["pontuacao"] for r in registros)
    media = total / len(registros)
    registros_ordenados = sorted(registros, key=lambda x: x["data"], reverse=True)

    return {
        "pontuacao_media": round(media, 2),
        "pontuacao_total": round(total, 2),
        "dias_com_dados": len(registros),
        "detalhes": [
            {"data": str(r["data"]), "pontuacao": r["pontuacao"]}
            for r in registros_ordenados[:10]
        ],
    }


def _calcular_alerta(rec_prod: dict, banco_horas: dict, inspecao: dict | None) -> list[str]:
    """Regras de alerta — lógica pura (testável)."""
    alertas = []
    if rec_prod.get("reabriu_total", 0) >= LIMITE_REABERTURA:
        alertas.append("recorrência de reabertura acima do limite")
    if (banco_horas.get("saldo") or 0) > LIMITE_BANCO_HORAS:
        alertas.append("saldo de banco de horas acima do limite semanal")
    if inspecao and (inspecao.get("pontuacao") or 0) < META_INSPECAO:
        alertas.append("pontuação de inspeção abaixo da meta")
    return alertas
