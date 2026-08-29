"""ETL do Excel de recorrência ("Analítico", export manual) para o Postgres.

Estrutura do arquivo (validado em recorrencia_2026-08_campina-grande.xlsx):
- aba "Analitico";
- linha 0: títulos de grupo ("OS DO MÊS", "OS ANTERIOR (RECORRÊNCIA — 30 DIAS)");
- linha 1: headers reais (Protocolo, Data abertura, ..., É recorrência?);
- dados a partir da linha 2.

Enriquecimento: `tecnico` resolvido por join `Protocolo` = `os` contra o
Postgres já sincronizado pelo Proxxima (não chama API externa). Protocolos fora
da janela do GetAll podem ficar sem técnico — esperado.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.ocorrencia_recorrencia import OcorrenciaRecorrencia
from app.models.solicitacao_servico import SolicitacaoServico

logger = logging.getLogger(__name__)

ABA = "Analitico"
HEADER_LINHA = 1

COLUNAS_ESPERADAS = [
    "Protocolo",
    "Data abertura",
    "Data fechamento",
    "Problema do fechamento",
    "Cidade",
    "Unidade",
    "Etiqueta",
    "Protocolo anterior",
    "Data abertura anterior",
    "Data fechamento anterior",
    "Problema do fechamento anterior",
    "Dias entre as OS",
    "É recorrência?",
]


class EstruturaInvalidaError(ValueError):
    """O Excel não tem as colunas esperadas do analítico de recorrência."""


def _ler_excel(caminho: str | Path) -> pd.DataFrame:
    df = pd.read_excel(caminho, sheet_name=ABA, header=HEADER_LINHA)
    df.columns = [str(c).strip() for c in df.columns]
    faltantes = [c for c in COLUNAS_ESPERADAS if c not in df.columns]
    if faltantes:
        raise EstruturaInvalidaError(f"Colunas ausentes no analítico: {faltantes}")
    return df


def _as_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value).strip() or None


def _as_protocolo(value: Any) -> str | None:
    """Converte protocolo/OS para string sem o sufixo '.0' de float do pandas."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    texto = str(value).strip()
    if texto.endswith(".0") and texto[:-2].isdigit():
        return texto[:-2]
    return texto or None


def _as_datetime(value: Any):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    try:
        return pd.to_datetime(value).to_pydatetime()
    except (ValueError, TypeError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _mapa_protocolo_tecnico_em_lotes(
    protocolos: list[str], buscar: Any, lote: int = 1000
) -> dict[str, str]:
    """Monta o mapa protocolo -> técnico chamando `buscar(lote)` por bloco.

    `buscar` recebe uma lista de protocolos e devolve `{protocolo: tecnico}`
    apenas para os que tiverem técnico resolvido (None fica de fora).
    Extraído como função pura para ser testável sem banco.
    """
    mapa: dict[str, str] = {}
    for i in range(0, len(protocolos), lote):
        mapa.update(buscar(protocolos[i : i + lote]))
    return mapa


def _buscar_mapa_protocolo_tecnico(db: Session, protocolos: list[str], lote: int = 1000) -> dict[str, str]:
    """Mapa protocolo -> técnico via join com o Postgres (GetAll já sincronizado)."""

    def _buscar(lote_protocolos: list[str]) -> dict[str, str]:
        linhas = db.execute(
            select(SolicitacaoServico.os, SolicitacaoServico.tecnico).where(
                SolicitacaoServico.os.in_(lote_protocolos),
                SolicitacaoServico.tecnico.isnot(None),
            )
        ).all()
        return {os_: tecnico for os_, tecnico in linhas}

    return _mapa_protocolo_tecnico_em_lotes(protocolos, _buscar, lote=lote)


def importar_recorrencia(caminho: str | Path, db: Session) -> dict[str, int]:
    """Importa o analítico de recorrência em `ocorrencia_recorrencia`.

    Upsert por `protocolo` (chave única): em execuções seguintes (o job roda
    diariamente), os protocolos já existentes são atualizados, não duplicados.
    Retorna contagens para log.
    """
    df = _ler_excel(caminho)
    protocolos = [p for p in (_as_protocolo(v) for v in df["Protocolo"]) if p]

    mapa_tecnico = _buscar_mapa_protocolo_tecnico(db, protocolos)

    importados = 0
    sem_tecnico = 0
    por_protocolo: dict[str, dict] = {}

    for _, row in df.iterrows():
        protocolo = _as_protocolo(row["Protocolo"])
        if not protocolo:
            continue
        e_recorrencia = (_as_str(row["É recorrência?"]) or "").upper() == "SIM"
        tecnico = mapa_tecnico.get(protocolo)
        if tecnico is None:
            sem_tecnico += 1

        por_protocolo[protocolo] = {
            "protocolo": protocolo,
            "data_abertura": _as_datetime(row.get("Data abertura")),
            "data_fechamento": _as_datetime(row.get("Data fechamento")),
            "problema_fechamento": _as_str(row.get("Problema do fechamento")),
            "cidade": _as_str(row.get("Cidade")),
            "unidade": _as_str(row.get("Unidade")),
            "etiqueta": _as_str(row.get("Etiqueta")),
            "protocolo_anterior": _as_protocolo(row.get("Protocolo anterior")),
            "data_abertura_anterior": _as_datetime(row.get("Data abertura anterior")),
            "data_fechamento_anterior": _as_datetime(row.get("Data fechamento anterior")),
            "problema_fechamento_anterior": _as_str(row.get("Problema do fechamento anterior")),
            "dias_entre_os": _as_int(row.get("Dias entre as OS")),
            "e_recorrencia": e_recorrencia,
            "tecnico": tecnico,
        }
        importados += 1

    if por_protocolo:
        cadastros = [por_protocolo[p] for p in protocolos if p in por_protocolo]
        colunas = [k for k in cadastros[0]]
        stmt = pg_insert(OcorrenciaRecorrencia).values(cadastros)
        stmt = stmt.on_conflict_do_update(
            index_elements=[OcorrenciaRecorrencia.protocolo],
            set_={k: stmt.excluded[k] for k in colunas},
        )
        db.execute(stmt)
        db.commit()

    logger.info(
        "[recorrencia] %d importadas, %d sem técnico resolvido (fora do lookback)",
        importados,
        sem_tecnico,
    )
    return {"importadas": importados, "sem_tecnico": sem_tecnico, "com_recorrencia": sum(
        1 for r in por_protocolo.values() if r["e_recorrencia"]
    )}
