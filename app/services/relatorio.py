"""Geração de relatório semanal em .docx.

Reaproveita a lógica de cruzamento do Sprint 4 (buscar_produtividade,
buscar_metricas_recorrencia, buscar_banco_horas_unidade, etc.) e gera
um documento Word com o resumo da unidade no período.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ocorrencia_recorrencia import OcorrenciaRecorrencia
from app.models.relatorio import Relatorio
from app.models.solicitacao_servico import SolicitacaoServico
from app.services.cruzamento import (
    buscar_banco_horas_unidade,
    buscar_infracoes_unidade,
    normalizar_unidade,
)

_DIR_RELATORIOS = Path(settings.dir_relatorios or "relatorios")


def _ensure_dir() -> Path:
    _DIR_RELATORIOS.mkdir(parents=True, exist_ok=True)
    return _DIR_RELATORIOS


def _addTitulo(doc: Document, texto: str) -> None:
    h = doc.add_heading(texto, level=1)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)


def _addSecao(doc: Document, titulo: str) -> None:
    h = doc.add_heading(titulo, level=2)
    for run in h.runs:
        run.font.size = Pt(12)


def _addParagrafo(doc: Document, texto: str, negrito: bool = False) -> None:
    p = doc.add_paragraph()
    run = p.add_run(texto)
    run.bold = negrito
    run.font.size = Pt(10)


def _addTabela(doc: Document, cabecalhos: list[str], linhas: list[list[str]]) -> None:
    if not linhas:
        _addParagrafo(doc, "  Nenhum registro no período.")
        return
    tabela = doc.add_table(rows=1 + len(linhas), cols=len(cabecalhos))
    tabela.style = "Light Grid Accent 1"
    for i, h in enumerate(cabecalhos):
        cell = tabela.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)
    for r, linha in enumerate(linhas):
        for c, valor in enumerate(linha):
            cell = tabela.rows[r + 1].cells[c]
            cell.text = str(valor)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)


def _buscar_status_unidade(db: Session, unidade_normalizada: str, periodo_de: date, periodo_ate: date) -> dict:
    """Agrega backlog + produtividade + canceladas de uma unidade no período."""
    naturezas_excluidas = ("RECOLHIMENTO", "RECOLHIMENTO AGENDADO")

    abertas = db.scalar(
        select(func.count())
        .select_from(SolicitacaoServico)
        .where(
            (SolicitacaoServico.unidade.ilike(f"%{unidade_normalizada}%"))
            & (SolicitacaoServico.status.notilike("Fechada%"))
            & (SolicitacaoServico.status.ilike("Aberta%"))
            & (SolicitacaoServico.natureza.is_not(None))
            & (SolicitacaoServico.natureza.notin_(naturezas_excluidas))
            & (SolicitacaoServico.natureza != "")
        )
    ) or 0

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

    return {
        "abertas": abertas,
        "fech_prod": fech_prod,
        "fech_improd": fech_improd,
        "canceladas": canceladas,
        "recorrencias": recorrencias,
    }


def _buscar_top_recorrencia(db: Session, unidade_normalizada: str, periodo_de: date, periodo_ate: date, limite: int = 10) -> list[dict]:
    """Top técnicos da unidade com mais recorrências no período."""
    from sqlalchemy import Integer

    sub = (
        select(
            OcorrenciaRecorrencia.tecnico,
            func.count().label("total"),
            func.sum(func.cast(OcorrenciaRecorrencia.e_recorrencia, Integer)).label("reaberturas"),
        )
        .where(
            OcorrenciaRecorrencia.data_abertura >= periodo_de,
            OcorrenciaRecorrencia.data_abertura <= periodo_ate,
            OcorrenciaRecorrencia.tecnico.isnot(None),
            OcorrenciaRecorrencia.unidade.ilike(f"%{unidade_normalizada}%"),
        )
        .group_by(OcorrenciaRecorrencia.tecnico)
        .order_by(func.sum(func.cast(OcorrenciaRecorrencia.e_recorrencia, Integer)).desc())
        .limit(limite)
    )

    rows = db.execute(sub).all()
    return [
        {"tecnico": r.tecnico, "total": r.total, "reaberturas": int(r.reaberturas or 0)}
        for r in rows
    ]


def _buscar_top_he(db: Session, unidade_normalizada: str, periodo_de: date, periodo_ate: date) -> list[dict]:
    """Top técnicos com mais HE (via snapshots do painel-ope)."""
    from app.models.banco_horas_semanal import BancoHorasSemanal
    from app.services.cruzamento import normalizar_unidade as _norm

    he_por_tecnico: dict[str, float] = {}
    snaps = (
        db.scalars(
            select(BancoHorasSemanal)
            .where(
                BancoHorasSemanal.semana_ate >= periodo_de,
                BancoHorasSemanal.semana_de <= periodo_ate,
            )
        ).all()
    )
    for snap in snaps:
        payload = snap.payload or {}
        for item in payload.get("rankTecHE") or []:
            if isinstance(item, dict):
                nome = item.get("nome", "")
                he = float(item.get("heHoras") or 0)
                he_por_tecnico[nome] = he_por_tecnico.get(nome, 0) + he

    ordenados = sorted(he_por_tecnico.items(), key=lambda x: x[1], reverse=True)[:10]
    return [{"tecnico": nome, "he_horas": round(he, 2)} for nome, he in ordenados]


def gerar_relatorio_semanal(
    db: Session,
    unidade: str,
    periodo_de: date,
    periodo_ate: date,
) -> Relatorio:
    """Gera relatório semanal em .docx e salva no disco + banco.

    Retorna o modelo Relatorio com id e caminho preenchidos.
    """
    unidade_norm = normalizar_unidade(unidade)
    titulo = f"Relatório Semanal — {unidade_norm} ({periodo_de.strftime('%d/%m/%Y')} a {periodo_ate.strftime('%d/%m/%Y')})"

    # Coleta dados via cruzamento
    status = _buscar_status_unidade(db, unidade_norm, periodo_de, periodo_ate)
    bh = buscar_banco_horas_unidade(db, unidade_norm, periodo_de, periodo_ate)
    infracoes = buscar_infracoes_unidade(db, unidade_norm, periodo_de, periodo_ate)
    top_rec = _buscar_top_recorrencia(db, unidade_norm, periodo_de, periodo_ate)
    top_he = _buscar_top_he(db, unidade_norm, periodo_de, periodo_ate)

    # Monta documento
    doc = Document()
    _addTitulo(doc, titulo)

    _addSecao(doc, "Resumo Geral")
    _addParagrafo(doc, f"Unidade: {unidade_norm}")
    _addParagrafo(doc, f"Período: {periodo_de.strftime('%d/%m/%Y')} a {periodo_ate.strftime('%d/%m/%Y')}")
    _addParagrafo(doc, f"Backlog (abertas agora): {status['abertas']}")
    _addParagrafo(doc, f"Fechadas produtivas: {status['fech_prod']}")
    _addParagrafo(doc, f"Fechadas improdutivas: {status['fech_improd']}")
    _addParagrafo(doc, f"Canceladas: {status['canceladas']}")
    _addParagrafo(doc, f"Horas Extras: {bh['he_horas']:.2f}h")
    _addParagrafo(doc, f"Infrações: {infracoes}")
    _addParagrafo(doc, f"Recorrências (reaberturas): {status['recorrencias']}")

    _addSecao(doc, "Top Técnicos — Recorrência")
    if top_rec:
        _addTabela(
            doc,
            ["Técnico", "Protocolos", "Reaberturas"],
            [[r["tecnico"], str(r["total"]), str(r["reaberturas"])] for r in top_rec],
        )
    else:
        _addParagrafo(doc, "  Nenhuma recorrência registrada no período.")

    _addSecao(doc, "Top Técnicos — Horas Extras")
    if top_he:
        _addTabela(
            doc,
            ["Técnico", "HE (h)"],
            [[r["tecnico"], f"{r['he_horas']:.2f}"] for r in top_he],
        )
    else:
        _addParagrafo(doc, "  Nenhum registro de HE no período.")

    _addSecao(doc, "Observações")
    _addParagrafo(doc, "Relatório gerado automaticamente pelo Agente OPE.")
    _addParagrafo(doc, "Dados fonte: Proxxima (solicitações), painel-ope (HE/infrações), Excel de recorrência.")
    _addParagrafo(doc, "Para dúvidas, consulte o agente operacoes no opencode.")

    # Salva em disco
    _dir = _ensure_dir()
    nome_arquivo = f"relatorio_{unidade_norm.replace(' ', '_')}_{periodo_de}_{periodo_ate}.docx"
    caminho = _dir / nome_arquivo
    doc.save(str(caminho))

    # Registra no banco
    reg = Relatorio(
        titulo=titulo,
        unidade=unidade_norm,
        periodo_de=periodo_de.isoformat(),
        periodo_ate=periodo_ate.isoformat(),
        nome_arquivo=nome_arquivo,
        caminho=str(caminho),
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)

    return reg
