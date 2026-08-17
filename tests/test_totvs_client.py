"""Testes do client TOTVS Analytics (Sprint 7).

Cobre: parse_xtab_data, constantes de report/dashboard, e lógica de extração.
"""

from app.services.totvs_client import (
    DASHBOARD_KPI,
    DASHBOARD_PREMIACAO_SUPERVISOR,
    REPORT_KPI_REPAROS,
    REPORT_PREMIACAO_SUPERVISOR,
    WORKSPACE,
    TotvsClient,
)


class TestParseXtabData:
    """Testa a conversão de xtab_data (GoodData cross-tab) para lista de dicts."""

    def test_kpi_format(self):
        """Formato real do KPI de Reparos."""
        xtab = {
            "columns": {
                "lookups": [
                    {"1": "Reparos Encerrados", "2": "Reparos Até 24h %", "0": "Reparos Até 24h"}
                ]
            },
            "rows": {"lookups": [{"0": "Values"}]},
            "data": [["531", "758", "0.700527704485488"]],
            "size": {"columns": 3, "rows": 1},
        }
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 1
        assert resultado[0]["Reparos Até 24h"] == "531"
        assert resultado[0]["Reparos Encerrados"] == "758"
        assert resultado[0]["Reparos Até 24h %"] == "0.700527704485488"
        assert resultado[0]["linha"] == "Values"

    def test_single_metric(self):
        """Formato com uma única métrica (update timestamp)."""
        xtab = {
            "columns": {
                "lookups": [{"0": "."}]
            },
            "rows": {"lookups": [{"0": "."}]},
            "data": [["160408545"]],
            "size": {"columns": 1, "rows": 1},
        }
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 1
        assert resultado[0]["."] == "160408545"

    def test_empty_data(self):
        """Dados vazios."""
        xtab = {
            "columns": {"lookups": [{}]},
            "rows": {"lookups": [{}]},
            "data": [],
            "size": {"columns": 0, "rows": 0},
        }
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert resultado == []

    def test_multi_row(self):
        """Múltiplas linhas."""
        xtab = {
            "columns": {
                "lookups": [{"0": "Nome", "1": "Valor"}]
            },
            "rows": {"lookups": [{"0": "Linha A"}, {"1": "Linha B"}]},
            "data": [["A", "100"], ["B", "200"]],
            "size": {"columns": 2, "rows": 2},
        }
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 2
        assert resultado[0]["Nome"] == "A"
        assert resultado[0]["Valor"] == "100"
        assert resultado[0]["linha"] == "Linha A"
        assert resultado[1]["Nome"] == "B"
        assert resultado[1]["Valor"] == "200"
        assert resultado[1]["linha"] == "Linha B"

    def test_missing_lookups(self):
        """Lookups ausentes não quebra."""
        xtab = {
            "columns": {},
            "rows": {},
            "data": [["valor1", "valor2"]],
            "size": {"columns": 2, "rows": 1},
        }
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 1
        assert resultado[0]["col_0"] == "valor1"
        assert resultado[0]["col_1"] == "valor2"


class TestConstantesTotvs:
    """Verifica que as constantes de ID estão corretas."""

    def test_workspace(self):
        assert WORKSPACE == "x1axmpyn93u81uio68w00y4arjxjgbq1"

    def test_dashboard_kpi(self):
        assert DASHBOARD_KPI == "124470"

    def test_report_kpi(self):
        assert REPORT_KPI_REPAROS == "4890627"

    def test_dashboard_premiacao(self):
        assert DASHBOARD_PREMIACAO_SUPERVISOR == "2278082"

    def test_report_premiacao(self):
        assert REPORT_PREMIACAO_SUPERVISOR == "1464793"
