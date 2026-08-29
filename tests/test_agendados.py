"""Testes de atendimentos agendados (data_Hora_Agendamento_OS).

Cobre a agregacao _agendados_por_dia com fake DB (mesmo padrao dos outros
testes - sem banco real), a regra de "com equipe" e o mapeamento da coluna
agendamento no sync do Proxxima.
"""

from datetime import date

from app.jobs.sync_proxxima import _map_payload
from app.models.solicitacao_servico import SolicitacaoServico
from app.routers.diagnostico import _agendados_por_dia, _tem_equipe

DIA = date(2026, 8, 29)


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


def _servico(
    tecnico=None,
    equipe_matricula="",
    natureza=None,
    status="Aberta Aguardando Atendimento",
):
    return SolicitacaoServico(
        unidade="REG-CAMPINA GRANDE | PB",
        tecnico=tecnico,
        natureza=natureza,
        status=status,
        payload={"equipe_Matricula": equipe_matricula},
    )


class TestAgendadosPorDia:
    def test_agrega_total_com_sem_equipe_e_por_natureza(self):
        db = FakeDB(
            [
                _servico(tecnico="TEC A", natureza="SEM ACESSO"),
                _servico(equipe_matricula="447311", natureza="SEM ACESSO"),
                _servico(tecnico="TEC B", natureza="DEFEITO INTERNO"),
                _servico(natureza="DEFEITO INTERNO"),
            ]
        )
        res = _agendados_por_dia(db, "CAMPINA GRANDE", DIA)
        assert res.unidade == "CAMPINA GRANDE"
        assert res.total == 4
        assert res.com_equipe == 3
        assert res.sem_equipe == 1
        por_nat = {a.natureza: (a.total, a.com_equipe) for a in res.por_natureza}
        assert por_nat["DEFEITO INTERNO"] == (2, 1)
        assert por_nat["SEM ACESSO"] == (2, 2)

    def test_ordena_natureza_por_total_desc(self):
        db = FakeDB(
            [
                _servico(tecnico="T", natureza="X"),
                _servico(tecnico="T", natureza="Y"),
                _servico(tecnico="T", natureza="X"),
            ]
        )
        res = _agendados_por_dia(db, "CAMPINA GRANDE", DIA)
        assert [a.natureza for a in res.por_natureza] == ["X", "Y"]

    def test_sem_registros(self):
        res = _agendados_por_dia(FakeDB([]), "LAGOA SECA", DIA)
        assert res.unidade == "LAGOA SECA"
        assert res.total == 0
        assert res.com_equipe == 0
        assert res.sem_equipe == 0
        assert res.por_natureza == []

    def test_natureza_vazia_vira_rotulo(self):
        res = _agendados_por_dia(FakeDB([_servico(tecnico="T", natureza=None)]), "CAMPINA GRANDE", DIA)
        assert res.por_natureza[0].natureza == "SEM NATUREZA"


class TestTemEquipe:
    def test_por_tecnico(self):
        assert _tem_equipe(_servico(tecnico="TEC A")) is True

    def test_por_matricula(self):
        assert _tem_equipe(_servico(equipe_matricula="447311")) is True

    def test_sem_equipe(self):
        assert _tem_equipe(_servico()) is False


class TestMapeamentoAgendamento:
    def test_extrai_agendamento_do_payload(self):
        m = _map_payload(
            {
                "numero_Obra": "8762147/1",
                "status_Execucao": "Aberta Aguardando Atendimento",
                "data_Hora_Agendamento_OS": "29/08/2026 09:55",
                "grupo_Area": "REG-CAMPINA GRANDE | PB",
            }
        )
        assert m["agendamento"] is not None
        assert m["agendamento"].strftime("%d/%m/%Y %H:%M") == "29/08/2026 09:55"

    def test_agendamento_vazio_vira_none(self):
        m = _map_payload(
            {
                "numero_Obra": "8762147/1",
                "status_Execucao": "Aberta Aguardando Agendamento",
                "data_Hora_Agendamento_OS": "",
            }
        )
        assert m["agendamento"] is None