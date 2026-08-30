"""Cliente da planilha pública de Banco de Horas (Google Sheets publicada como web).

Fonte: https://docs.google.com/spreadsheets/d/e/.../pub (aba HISTORICO_REG03,
pública, sem cookie — substitui o painel-ope como fonte de banco de horas/HE).

Estrutura esperada (validação explícita, ponto frágil):
    DATA,NOME,UNIDADE,COORDENADOR,SUPERVISOR,CARGO,TIPO,SALDO,VARIACAO,STATUS
    SALDO em formato brasileiro (vírgula decimal, ex.: "7,55").

O Google publica o CSV às vezes em cp1252 — decodificamos de forma robusta.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

COLUNAS_OBRIGATORIAS = ("DATA", "NOME", "UNIDADE", "SALDO")

DATA_FORMATOS = ("%d/%m/%Y",)  # formato dd/mm/yyyy observado no HISTORICO


class BancoHorasSheetsError(Exception):
    """Payload da planilha público com formato inesperado."""


def _decodificar(conteudo: bytes) -> str:
    """Decodifica o CSV tolerando utf-8 (com/sem BOM) e cp1252/latin-1."""
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("utf-8", errors="replace")


def parse_saldo_csv(texto: str, origem: str = "") -> list[dict[str, Any]]:
    """Converte o CSV em linhas brutas, validando as colunas obrigatórias.

    Lança ``BancoHorasSheetsError`` se faltar alguma coluna esperada.
    """
    leitor = csv.DictReader(io.StringIO(texto))
    colunas = [str(c or "").strip().upper().replace("\ufeff", "") for c in (leitor.fieldnames or [])]
    faltam = [c for c in COLUNAS_OBRIGATORIAS if c not in colunas]
    if faltam:
        raise BancoHorasSheetsError(
            f"Planilha de banco de horas sem colunas obrigatórias {faltam}. "
            f"Encontradas: {colunas} (origem: {origem})"
        )

    linhas: list[dict[str, Any]] = []
    for raw in leitor:
        linha = {
            str(k or "").strip().upper().replace("\ufeff", ""): (v or "").strip()
            for k, v in raw.items()
        }
        linhas.append(linha)
    logger.info("[banco-horas] parse CSV: %d linhas (origem: %s)", len(linhas), origem)
    return linhas


def parse_data_br(valor: Any) -> date | None:
    """Converte DATA dd/mm/yyyy em date; None se ausente/ilegível."""
    if valor is None or not str(valor).strip():
        return None
    for fmt in DATA_FORMATOS:
        try:
            return datetime.strptime(str(valor).strip(), fmt).date()
        except ValueError:
            continue
    logger.warning("[banco-horas] DATA no formato inesperado: %r", valor)
    return None


def parse_saldo_br(valor: Any) -> float | None:
    """Converte SALDO brasileiro ('7,55' ou '1.000,00') em float; None se vazio."""
    if valor is None or not str(valor).strip():
        return None
    txt = str(valor).strip().replace(".", "").replace(",", ".")
    try:
        return round(float(txt), 2)
    except ValueError:
        logger.warning("[banco-horas] SALDO ilegível: %r", valor)
        return None


def _texto_ou_none(valor: Any) -> str | None:
    if valor is None or not str(valor).strip():
        return None
    return str(valor)


class BancoHorasSheetsClient:
    """Busca o CSV público via HTTP (para o job de sync)."""

    def __init__(self, url: str | None = None):
        self.base_url = url or ""

    def fetch_saldo(self, url: str | None = None) -> list[dict[str, Any]]:
        from app.config import settings

        alvo = url or self.base_url or settings.banco_horas_saldo_url
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(alvo)
            resp.raise_for_status()
        return parse_saldo_csv(_decodificar(resp.content), origem=alvo)