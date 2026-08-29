"""Testes dos endpoints de ranking e recorrência por problema (painel Operações).

Cobre: categorizar_problema (regras puras), aggregation _ranking_recorrencia e
_por_problema com fake DB (mesmo padrão dos outros testes — sem banco real).
"""

from datetime import date

from app.routers.recorrencia import (
    MAPA_CATEGORIA_RECORRENCIA,
    _por_problema,
    _ranking_recorrencia,
    categorizar_problema,
)


class FakeResult:
    def __init__(self, linhas):
        self._linhas = linhas

    def all(self):
        return self._linhas


class FakeDB:
    """Devolve linhas/valores configurados — não executa SQL de verdade."""

    def __init__(self, linhas=None, total=0):
        self.linhas = linhas or []
        self.total = total

    def execute(self, stmt):
        return FakeResult(self.linhas)

    def scalar(self, stmt):
        return self.total


DE = date(2026, 8, 1)
ATE = date(2026, 8, 31)


# ── categorizar_problema ─────────────────────────────────────────────


class TestCategorizarProblema:
    def test_campo_default(self):
        assert categorizar_problema("OPERAÇÕES - PROBLEMA NO CONECTOR") == "culpa_do_campo"

    def test_campo_outra_causa(self):
        assert categorizar_problema("OPERAÇÕES - SINAL ALTO") == "culpa_do_campo"

    def test_rede_externa(self):
        assert categorizar_problema("OPERAÇÕES - ORIGEM REDES") == "rede_externa"

    def test_rede_infra(self):
        assert categorizar_problema("ORIGEM INFRA") == "rede_externa"

    def test_administrativo_desistiu(self):
        assert categorizar_problema("OPERAÇÕES - CLIENTE DESISTIU") == "administrativo"

    def test_administrativo_massiva(self):
        assert categorizar_problema("CLIENTE EM MASSIVA ABERTA") == "administrativo"

    def test_none(self):
        assert categorizar_problema(None) == "sem_problema"

    def test_case_insensitive(self):
        assert categorizar_problema("cliente desistiu") == "administrativo"

    def test_regras_presentes_no_mapa(self):
        assert set(MAPA_CATEGORIA_RECORRENCIA) == {"administrativo", "rede_externa"}


# ── _ranking_recorrencia ─────────────────────────────────────────────


class TestRankingRecorrencia:
    def test_ordena_decrescente_e_aplica_top(self):
        linhas = [
            ("TEC A", 30, 23),
            ("TEC B", 20, 18),
            ("TEC C", 10, 5),
        ]
        res = _ranking_recorrencia(
            FakeDB(linhas=linhas, total=46), "UNIDADE CAMPINA GRANDE", DE, ATE, top=2
        )
        assert [i.tecnico for i in res["ranking"]] == ["TEC A", "TEC B"]

    def test_acrescenta_os_no_analitico_e_taxa(self):
        res = _ranking_recorrencia(
            FakeDB(linhas=[("TEC A", 40, 10)], total=10), "CAMPINA GRANDE", DE, ATE, top=5
        )
        item = res["ranking"][0]
        assert item.os_no_analitico == 40
        assert item.taxa == 25.0

    def test_taxa_zero_se_sem_os(self):
        res = _ranking_recorrencia(
            FakeDB(linhas=[("TEC A", 0, 0)], total=0), "CAMPINA GRANDE", DE, ATE, top=5
        )
        assert res["ranking"][0].taxa == 0.0

    def test_ignora_linha_de_tecnico_none(self):
        res = _ranking_recorrencia(
            FakeDB(linhas=[(None, 5, 3), ("TEC B", 10, 2)], total=5), "CAMPINA GRANDE", DE, ATE, top=5
        )
        assert [i.tecnico for i in res["ranking"]] == ["TEC B"]

    def test_normaliza_unidade_e_traz_total(self):
        res = _ranking_recorrencia(
            FakeDB(linhas=[("TEC A", 1, 1)], total=195), "REG-CAMPINA GRANDE | PB", DE, ATE, top=5
        )
        assert res["unidade"] == "CAMPINA GRANDE"
        assert res["total_recorrencias"] == 195
        assert res["periodo_de"] == DE and res["periodo_ate"] == ATE


# ── _por_problema ────────────────────────────────────────────────────


class TestPorProblema:
    def test_agrupa_e_percentual(self):
        linhas = [
            ("OPERAÇÕES - PROBLEMA NO CONECTOR", 48),
            ("OPERAÇÕES - ORIGEM REDES", 12),
        ]
        res = _por_problema(FakeDB(linhas=linhas), "CAMPINA GRANDE", DE, ATE)
        assert res["total_recorrencias"] == 60
        assert res["por_problema"][0].problema == "OPERAÇÕES - PROBLEMA NO CONECTOR"
        assert res["por_problema"][0].pct == 80.0
        assert res["por_problema"][1].pct == 20.0

    def test_problema_none_vira_rotulo(self):
        res = _por_problema(FakeDB(linhas=[(None, 3)]), "CAMPINA GRANDE", DE, ATE)
        assert res["por_problema"][0].problema == "SEM PROBLEMA REGISTRADO"

    def test_resumo_3_categorias(self):
        linhas = [
            ("OPERAÇÕES - PROBLEMA NO CONECTOR", 48),
            ("OPERAÇÕES - ORIGEM REDES", 12),
            ("OPERAÇÕES - CLIENTE DESISTIU", 10),
        ]
        res = _por_problema(FakeDB(linhas=linhas), "CAMPINA GRANDE", DE, ATE)
        resumo = {c: (v.recorrencias, v.pct) for c, v in res["resumo_categorias"].items()}
        assert resumo == {
            "administrativo": (10, 14.3),
            "culpa_do_campo": (48, 68.6),
            "rede_externa": (12, 17.1),
        }

    def test_sem_problema_no_resumo(self):
        res = _por_problema(FakeDB(linhas=[(None, 3)]), "CAMPINA GRANDE", DE, ATE)
        resumo = {c: (v.recorrencias, v.pct) for c, v in res["resumo_categorias"].items()}
        assert resumo == {"sem_problema": (3, 100.0)}