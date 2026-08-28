"""Testes do client TOTVS Analytics (Sprint 7).

Cobre: parse_xtab_data, constantes de report/dashboard, e lógica de extração.
"""

from app.services.totvs_client import (
    DASHBOARD_KPI,
    DASHBOARD_PREMIACAO_SUPERVISOR,
    REPORT_KPI_REPAROS,
    REPORT_PREMIACAO_SUPERVISOR,
    REPORT_PONTUACAO_DIA_TECNICO,
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


class TestParseHierarquico:
    """Testa o parser hierárquico (árvore GoodData com offset first/last)."""

    @staticmethod
    def _make_xtab(rows_children, rows_lookups, col_children, col_lookups, data):
        return {
            "rows": {
                "tree": {"id": "root", "type": "normal", "first": 0,
                         "last": len(data) - 1, "index": {},
                         "children": rows_children},
                "lookups": rows_lookups,
            },
            "columns": {
                "tree": {"id": "root", "type": "normal", "first": 0,
                         "last": len(data[0]) - 1, "index": {},
                         "children": col_children},
                "lookups": col_lookups,
            },
            "data": data,
        }

    @staticmethod
    def _make_group(group_id, first, last, tech_map):
        """Cria um nó de grupo (unidade) com index local 0-based."""
        idx = {tid: [i] for i, (tid, _) in enumerate(tech_map)}
        children = [
            {"id": tid, "type": "normal", "first": i, "last": i,
             "index": {}, "children": []}
            for i, (tid, _) in enumerate(tech_map)
        ]
        return {"id": group_id, "type": "normal", "first": first,
                "last": last, "index": idx, "children": children}

    @staticmethod
    def _make_date(date_id, first, last, n_metrics=1):
        idx = {"metric_0": [i] for i in range(n_metrics)}
        return {"id": date_id, "type": "normal", "first": first,
                "last": last, "index": idx, "children": []}

    def test_offset_two_groups(self):
        """Dois grupos com offsets diferentes devem mapear todos os rows."""
        groups = [
            self._make_group("U1", first=0, last=1, tech_map=[
                ("T1", "TECNICO A"), ("T2", "TECNICO B"),
            ]),
            self._make_group("U2", first=2, last=3, tech_map=[
                ("T3", "TECNICO C"), ("T4", "TECNICO D"),
            ]),
        ]
        rows_lookups = [
            {"U1": "UNIDADE ALPHA", "U2": "UNIDADE BETA"},
            {"T1": "TECNICO A", "T2": "TECNICO B",
             "T3": "TECNICO C", "T4": "TECNICO D"},
        ]
        col_children = [self._make_date("D1", first=0, last=0)]
        col_lookups = [{"D1": "01/07/2026"}]
        data = [[10], [20], [30], [40]]

        xtab = self._make_xtab(groups, rows_lookups, col_children, col_lookups, data)
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 4
        by_tech = {r["tecnico"]: r for r in resultado}
        assert by_tech["TECNICO A"]["unidade"] == "UNIDADE ALPHA"
        assert by_tech["TECNICO A"]["pontuacao"] == "10"
        assert by_tech["TECNICO D"]["unidade"] == "UNIDADE BETA"
        assert by_tech["TECNICO D"]["pontuacao"] == "40"

    def test_offset_three_groups(self):
        """Três grupos: valida que offsets se acumulam corretamente."""
        groups = [
            self._make_group("U1", first=0, last=0, tech_map=[
                ("T1", "TEC A"),
            ]),
            self._make_group("U2", first=1, last=2, tech_map=[
                ("T2", "TEC B"), ("T3", "TEC C"),
            ]),
            self._make_group("U3", first=3, last=3, tech_map=[
                ("T4", "TEC D"),
            ]),
        ]
        rows_lookups = [
            {"U1": "GRUPO 1", "U2": "GRUPO 2", "U3": "GRUPO 3"},
            {"T1": "TEC A", "T2": "TEC B", "T3": "TEC C", "T4": "TEC D"},
        ]
        col_children = [self._make_date("D1", first=0, last=0)]
        col_lookups = [{"D1": "15/07/2026"}]
        data = [[100], [200], [300], [400]]

        xtab = self._make_xtab(groups, rows_lookups, col_children, col_lookups, data)
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 4
        by_tech = {r["tecnico"]: r for r in resultado}
        assert by_tech["TEC A"]["unidade"] == "GRUPO 1"
        assert by_tech["TEC B"]["unidade"] == "GRUPO 2"
        assert by_tech["TEC C"]["unidade"] == "GRUPO 2"
        assert by_tech["TEC D"]["unidade"] == "GRUPO 3"

    def test_col_offset_two_dates(self):
        """Duas datas com offsets diferentes nas colunas."""
        groups = [
            self._make_group("U1", first=0, last=0, tech_map=[
                ("T1", "TEC A"),
            ]),
        ]
        rows_lookups = [{"U1": "UNI"}, {"T1": "TEC A"}]
        col_children = [
            self._make_date("D1", first=0, last=0),
            self._make_date("D2", first=1, last=1),
        ]
        col_lookups = [{"D1": "01/07/2026", "D2": "02/07/2026"}]
        data = [[5, 15]]

        xtab = self._make_xtab(groups, rows_lookups, col_children, col_lookups, data)
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 2
        by_date = {r["data"]: r for r in resultado}
        assert by_date["01/07/2026"]["pontuacao"] == "5"
        assert by_date["02/07/2026"]["pontuacao"] == "15"

    def test_skip_zero_values(self):
        """Valores zero ou None são ignorados."""
        groups = [
            self._make_group("U1", first=0, last=1, tech_map=[
                ("T1", "TEC A"), ("T2", "TEC B"),
            ]),
        ]
        rows_lookups = [{"U1": "UNI"}, {"T1": "TEC A", "T2": "TEC B"}]
        col_children = [self._make_date("D1", first=0, last=0)]
        col_lookups = [{"D1": "01/07/2026"}]
        data = [["0"], ["10"]]

        xtab = self._make_xtab(groups, rows_lookups, col_children, col_lookups, data)
        resultado = TotvsClient.parse_xtab_data(xtab)
        assert len(resultado) == 1
        assert resultado[0]["tecnico"] == "TEC B"

    def test_no_empty_unidade(self):
        """Todas as linhas devem ter unidade preenchida (nenhum '')."""
        groups = [
            self._make_group("U1", first=0, last=1, tech_map=[
                ("T1", "TEC A"), ("T2", "TEC B"),
            ]),
            self._make_group("U2", first=2, last=2, tech_map=[
                ("T3", "TEC C"),
            ]),
        ]
        rows_lookups = [
            {"U1": "ALPHA", "U2": "BETA"},
            {"T1": "TEC A", "T2": "TEC B", "T3": "TEC C"},
        ]
        col_children = [self._make_date("D1", first=0, last=0)]
        col_lookups = [{"D1": "01/07/2026"}]
        data = [[10], [0], [30]]

        xtab = self._make_xtab(groups, rows_lookups, col_children, col_lookups, data)
        resultado = TotvsClient.parse_xtab_data(xtab)
        for r in resultado:
            assert r["unidade"] != "", f"Linha {r} tem unidade vazia"


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

    def test_report_pontuacao(self):
        assert REPORT_PONTUACAO_DIA_TECNICO == "2837323"
