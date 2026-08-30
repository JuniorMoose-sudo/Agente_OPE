"""Testes das funções puras do cruzamento (Sprint 7).

Cobre: normalizar_unidade, _is_aberta (sync_proxxima), _calcular_alerta,
e helpers de delta do relatório.
"""

from app.jobs.sync_proxxima import _is_aberta
from app.services.cruzamento import (
    LIMITE_BANCO_HORAS,
    LIMITE_REABERTURA,
    META_INSPECAO,
    _calcular_alerta,
    normalizar_unidade,
)


# ── normalizar_unidade ─────────────────────────────────────────────


class TestNormalizarUnidade:
    def test_reg_prefix(self):
        assert normalizar_unidade("REG-CAMPINA GRANDE") == "CAMPINA GRANDE"

    def test_unidade_prefix(self):
        assert normalizar_unidade("UNIDADE CAMPINA GRANDE") == "CAMPINA GRANDE"

    def test_pipe_suffix(self):
        assert normalizar_unidade("CAMPINA GRANDE | PB") == "CAMPINA GRANDE"

    def test_reg_e_pipe(self):
        assert normalizar_unidade("REG-LAGOA SECA | PB") == "LAGOA SECA"

    def test_ja_normalizado(self):
        assert normalizar_unidade("LAGOA SECA") == "LAGOA SECA"

    def test_none_vira_vazio(self):
        assert normalizar_unidade(None) == ""

    def test_string_vazia(self):
        assert normalizar_unidade("") == ""

    def test_espacos_extras(self):
        assert normalizar_unidade("  REG-CAMPINA GRANDE  ") == "CAMPINA GRANDE"

    def test_minusculas_com_prefixo_hifen(self):
        assert normalizar_unidade("reg-campina grande") == "CAMPINA GRANDE"

    def test_unidade_completa_real(self):
        assert normalizar_unidade("UNIDADE CAMPINA GRANDE _ LAGOA SECA") == "CAMPINA GRANDE _ LAGOA SECA"


# ── _is_aberta ─────────────────────────────────────────────────────


class TestIsAberta:
    def test_aberta_produtiva(self):
        assert _is_aberta("Aberta Produtiva") is True

    def test_aberta_improdutiva(self):
        assert _is_aberta("Aberta Improdutiva") is True

    def test_aberta_simples(self):
        assert _is_aberta("Aberta") is True

    def test_aberto(self):
        assert _is_aberta("aberto") is True

    def test_fechada_produtiva(self):
        assert _is_aberta("Fechada Produtiva") is False

    def test_fechada_improdutiva(self):
        assert _is_aberta("Fechada Improdutiva") is False

    def test_cancelado(self):
        assert _is_aberta("Cancelado") is False

    def test_cancelado_case_insensitive(self):
        assert _is_aberta("cancelado") is False

    def test_none(self):
        assert _is_aberta(None) is False

    def test_vazio(self):
        assert _is_aberta("") is False

    def test_status_desconhecido(self):
        # Qualquer status que não começa com "Fechada" e não é "Cancelado"
        assert _is_aberta("Em Andamento") is True


# ── _delta_str e _delta_pct (relatorio.py) ─────────────────────────


class TestDeltaStr:
    def test_igual(self):
        from app.services.relatorio import _delta_str
        assert _delta_str(10, 10) == "=0"

    def test_aumento(self):
        from app.services.relatorio import _delta_str
        assert _delta_str(15, 10) == "+5"

    def test_queda(self):
        from app.services.relatorio import _delta_str
        assert _delta_str(8, 15) == "-7"

    def test_zero_para_algo(self):
        from app.services.relatorio import _delta_str
        assert _delta_str(5, 0) == "+5"


class TestDeltaPct:
    def test_igual(self):
        from app.services.relatorio import _delta_pct
        assert _delta_pct(10, 10) == "0%"

    def test_aumento_50pct(self):
        from app.services.relatorio import _delta_pct
        assert _delta_pct(15, 10) == "+50%"

    def test_queda_50pct(self):
        from app.services.relatorio import _delta_pct
        assert _delta_pct(5, 10) == "-50%"

    def test_anterior_zero_com_algo(self):
        from app.services.relatorio import _delta_pct
        assert _delta_pct(5, 0) == "N/A"

    def test_anterior_e_atual_zero(self):
        from app.services.relatorio import _delta_pct
        assert _delta_pct(0, 0) == "=0"
