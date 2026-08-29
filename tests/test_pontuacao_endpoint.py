"""Testes da agregação de pontuação das equipes (endpoint /diagnostico/pontuacao).

Cobre: soma do dia e da semana por técnica, as metas (8/dia SEG-SEX e
40/semana, sem meta sáb/dom), a quebra diária e a ordenação. Sem banco (fake
DB no padrão do projeto).
"""

from datetime import date

from app.models.pontuacao_tecnico_dia import PontuacaoTecnicoDia
from app.routers.diagnostico import META_PONTOS_SEMANA, _agregar_pontuacao, _meta_dia

SEG = date(2026, 8, 24)
SEX = date(2026, 8, 28)
SAB = date(2026, 8, 29)
DOM = date(2026, 8, 30)


class FakeScalars:
    def __init__(self, linhas):
        self._linhas = linhas

    def all(self):
        return self._linhas


class FakeDB:
    def __init__(self, linhas):
        self.linhas = linhas

    def scalars(self, stmt):
        return FakeScalars(self.linhas)


def _linha(tecnico, dia, pontos, unidade="CAMPINA GRANDE", nao_pontua=False):
    return PontuacaoTecnicoDia(
        tecnico=tecnico,
        unidade="REG-CAMPINA GRANDE | PB" if unidade == "CAMPINA GRANDE" else "REG-LAGOA SECA | PB",
        data=dia,
        pontos=float(pontos),
        nao_pontua=nao_pontua,
    )


class TestMetaDia:
    def test_seg_a_sex_tem_meta(self):
        assert _meta_dia(SEG) == 8.0
        assert _meta_dia(SEX) == 8.0

    def test_sabado_e_domingo_sem_meta(self):
        assert _meta_dia(SAB) is None
        assert _meta_dia(DOM) is None


class TestAgregarPontuacao:
    def test_pontos_do_dia_e_da_semana_com_metas(self):
        linhas = [
            _linha("TEC A", SEG, 8.0),
            _linha("TEC A", TERC:=date(2026, 8, 25), 8.0),
            _linha("TEC A", SEX, 4.0),
            _linha("TEC B", SEG, 9.98),
            _linha("TEC B", SEX, 1.0),
        ]
        res = _agregar_pontuacao(FakeDB(linhas), "CAMPINA GRANDE", SEX)

        assert res.unidade == "CAMPINA GRANDE"
        assert res.data == SEX
        assert res.semana_de == date(2026, 8, 24)
        assert res.semana_ate == date(2026, 8, 30)
        assert res.meta_dia == 8.0
        assert res.meta_semana == META_PONTOS_SEMANA

        por_tecnico = {e.tecnico: e for e in res.equipes}
        assert por_tecnico["TEC A"].pontos_dia == 4.0
        assert por_tecnico["TEC A"].ponto_semana == 20.0
        assert por_tecnico["TEC A"].cumpre_meta_dia is False
        assert por_tecnico["TEC A"].cumpre_meta_semana is False  # 20 < 40
        assert [d.pontos for d in por_tecnico["TEC A"].dias] == [8.0, 8.0, 4.0]

        assert por_tecnico["TEC B"].pontos_dia == 1.0
        assert por_tecnico["TEC B"].ponto_semana == 10.98
        assert por_tecnico["TEC B"].cumpre_meta_dia is False

    def test_nao_pontua_flag_e_metas_no_fim_de_semana(self):
        linhas = [
            _linha("TEC A", SAB, 4.0, nao_pontua=True),
            _linha("TEC A", DOM, 0.0, nao_pontua=True),
        ]
        res = _agregar_pontuacao(FakeDB(linhas), "CAMPINA GRANDE", SAB)
        equipe = res.equipes[0]
        assert res.meta_dia is None
        assert equipe.cumpre_meta_dia is None
        assert equipe.nao_pontua is True
        assert equipe.ponto_semana == 4.0
        assert equipe.cumpre_meta_semana is False

    def test_cumpre_meta_semana_quando_chega_a_40(self):
        dias = [
            _linha("TEC A", date(2026, 8, 24) + __import__("datetime").timedelta(days=i), 8.0)
            for i in range(5)
        ]
        res = _agregar_pontuacao(FakeDB(dias), "CAMPINA GRANDE", SEX)
        assert res.equipes[0].ponto_semana == 40.0
        assert res.equipes[0].cumpre_meta_semana is True

    def test_sem_registros(self):
        res = _agregar_pontuacao(FakeDB([]), "LAGOA SECA", SEX)
        assert res.equipes == []
        assert res.total_pontos_dia == 0.0
        assert res.total_pontos_semana == 0.0

    def test_ordena_pela_semana_desc(self):
        linhas = [
            _linha("TEC A", SEG, 2.0),
            _linha("TEC B", SEG, 50.0),
            _linha("TEC C", SEG, 20.0),
        ]
        res = _agregar_pontuacao(FakeDB(linhas), "CAMPINA GRANDE", SEG)
        assert [e.tecnico for e in res.equipes] == ["TEC B", "TEC C", "TEC A"]

    def test_total_do_dia_soma_so_o_dia(self):
        linhas = [
            _linha("TEC A", SEG, 8.0),
            _linha("TEC A", SEX, 3.0),
            _linha("TEC B", SEX, 5.0),
        ]
        res = _agregar_pontuacao(FakeDB(linhas), "CAMPINA GRANDE", SEX)
        assert res.total_pontos_dia == 8.0
        assert res.total_pontos_semana == 16.0

    def test_resumo_omite_a_quebra_diaria(self):
        linhas = [
            _linha("TEC A", SEG, 8.0),
            _linha("TEC A", SEX, 4.0),
            _linha("TEC B", SEG, 9.98),
        ]
        res = _agregar_pontuacao(FakeDB(linhas), "CAMPINA GRANDE", SEX, resumo=True)
        por_tecnico = {e.tecnico: e for e in res.equipes}
        assert por_tecnico["TEC A"].dias == []
        assert por_tecnico["TEC A"].ponto_semana == 12.0  # soma continua
        assert por_tecnico["TEC A"].pontos_dia == 4.0
        assert por_tecnico["TEC B"].dias == []

    def test_sem_resumo_traz_os_dias(self):
        res = _agregar_pontuacao(FakeDB([_linha("TEC A", SEG, 8.0)]), "CAMPINA GRANDE", SEG, resumo=False)
        assert [d.pontos for d in res.equipes[0].dias] == [8.0]