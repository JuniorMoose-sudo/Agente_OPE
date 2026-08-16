"""Testes do ETL de recorrência — parsers, estrutura do Excel e join protocolo↔técnico.

Sem rede e sem Postgres: o join é testado com um "db" fake que simula a
consulta `select(os, tecnico) where os in (...)`.
"""

import io
from datetime import datetime

import pandas as pd
import pytest

from app.etl.recorrencia import (
    EstruturaInvalidaError,
    _as_datetime,
    _as_int,
    _as_protocolo,
    _as_str,
    _ler_excel,
    _mapa_protocolo_tecnico_em_lotes,
)

COLUNAS = [
    "Protocolo",
    "Data abertura",
    "Data fechamento",
    "Texto de abertura",
    "Texto de fechamento",
    "Problema do fechamento",
    "Cidade",
    "Unidade",
    "Etiqueta",
    "Protocolo anterior",
    "Data abertura anterior",
    "Data fechamento anterior",
    "Texto de abertura anterior",
    "Texto de fechamento anterior",
    "Problema do fechamento anterior",
    "Dias entre as OS",
    "É recorrência?",
]


def _fazer_excel(linhas: list[list]) -> bytes:
    """Monta um analítico em memória com a estrutura real (linha 0 = grupos, linha 1 = header)."""
    grupo = [None] * 17
    grupo[0] = "OS DO MÊS"
    grupo[9] = "OS ANTERIOR (RECORRÊNCIA — 30 DIAS)"
    dados = [grupo, COLUNAS] + linhas
    df = pd.DataFrame(dados)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Analitico", index=False, header=False)
    return buffer.getvalue()


class TestParsers:
    def test_as_str(self):
        assert _as_str(None) is None
        assert _as_str(float("nan")) is None
        assert _as_str("  abc  ") == "abc"

    def test_as_datetime_timestamp(self):
        valor = _as_datetime(pd.Timestamp("2026-08-01 08:03:53"))
        assert isinstance(valor, datetime)

    def test_as_datetime_invalido(self):
        assert _as_datetime(None) is None
        assert _as_datetime("lixo") is None

    def test_as_int(self):
        assert _as_int(15) == 15
        assert _as_int("7") == 7
        assert _as_int(None) is None
        assert _as_int("x") is None

    def test_as_protocolo_float_do_pandas(self):
        assert _as_protocolo(8682770.0) == "8682770"
        assert _as_protocolo("8688088.0") == "8688088"

    def test_as_protocolo_int_e_nulo(self):
        assert _as_protocolo(8687823) == "8687823"
        assert _as_protocolo(None) is None
        assert _as_protocolo(float("nan")) is None


class TestLerExcel:
    def test_estrutura_valida(self):
        conteudo = _fazer_excel([["8687823", None, None, None, None, "PROBLEMA", "CG|PB", "UNIDADE", "X", None, None, None, None, None, None, None, "NÃO"]])
        df = _ler_excel(io.BytesIO(conteudo))
        assert df.shape == (1, 17)
        assert "Protocolo" in df.columns

    def test_colunas_ausentes(self):
        conteudo = io.BytesIO()
        pd.DataFrame([["só", "algumas"]]).to_excel(
            conteudo, index=False, sheet_name="Analitico"
        )
        conteudo.seek(0)
        with pytest.raises(EstruturaInvalidaError):
            _ler_excel(conteudo)


class TestJoinProtocoloTecnico:
    """Testa a lógica de loteamento/mapeamento protocolo->técnico (sem banco)."""

    def _buscar(self, mapa: dict[str, str]):
        def _fn(lote: list[str]) -> dict[str, str]:
            return {p: mapa[p] for p in lote if p in mapa}

        return _fn

    def test_resolve_tecnico_por_protocolo(self):
        mapa = _mapa_protocolo_tecnico_em_lotes(
            ["8687823", "8687957"], self._buscar({"8687823": "FULANO DE TAL", "8687957": "BELTRANO"})
        )
        assert mapa == {"8687823": "FULANO DE TAL", "8687957": "BELTRANO"}

    def test_protocolo_fora_do_lookback_fica_sem_tecnico(self):
        mapa = _mapa_protocolo_tecnico_em_lotes(
            ["8687823", "9999999"], self._buscar({"8687823": "FULANO DE TAL"})
        )
        assert mapa == {"8687823": "FULANO DE TAL"}
        assert "9999999" not in mapa

    def test_tecnico_nulo_nao_entra_no_mapa(self):
        # Simula o WHERE tecnico IS NOT NULL: protocolo "2" não tem entrada.
        mapa = _mapa_protocolo_tecnico_em_lotes(
            ["1", "2"], self._buscar({"1": "A"})
        )
        assert "2" not in mapa

    def test_muitos_protocolos_loteia_em_blocos(self):
        base = {f"{i:07d}": f"TECNICO {i}" for i in range(2500)}
        mapa = _mapa_protocolo_tecnico_em_lotes(list(base.keys()), self._buscar(base), lote=1000)
        assert len(mapa) == 2500
