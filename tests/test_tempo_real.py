"""Testes do endpoint tempo_real: agregação por natureza das OS abertas.

O endpoint consulta a API Proxxima ao vivo via ``ProxximaClient``; aqui o
client é substituído por um fake, e validamos só a lógica de agregação.
"""

from datetime import datetime, timedelta

import pytest

from app.routers.diagnostico import _buscar_dados_tempo_real

HOJE = datetime.now().strftime("%d/%m/%Y")
ONTEM = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")


def _os(
    status="Aberta Aguardando Agendamento",
    natureza="CORRETIVO",
    grupo="REG-CAMPINA GRANDE",
    abertura=HOJE,
    encerramento="",
    sla="",
    responsavel="TECNICO TESTE",
) -> dict:
    return {
        "status_Execucao": status,
        "natureza": natureza,
        "grupo_Area": grupo,
        "dataHora_Abertura_OS": abertura,
        "dataHora_Encerramento_OS": encerramento,
        "sla": sla,
        "responsavel": responsavel,
    }


class _FakeClient:
    def __init__(self, servicos):
        self._servicos = servicos

    def fetch_servicos(self, **kwargs):
        return self._servicos

    def close(self):
        pass


@pytest.fixture
def fake_client(monkeypatch):
    def _instalar(servicos):
        fake = _FakeClient(servicos)
        monkeypatch.setattr(
            "app.services.proxxima_client.ProxximaClient",
            lambda *a, **k: fake,
        )
        return fake

    return _instalar


def test_abertas_por_natureza_conta_so_abertas_da_unidade(fake_client):
    """Só OS abertas da unidade entram na contagem por natureza:
    fechadas, canceladas e outras unidades ficam de fora."""
    fake_client([
        _os(natureza="SEM ACESSO"),
        _os(natureza="SEM ACESSO"),
        _os(natureza="CORRETIVO"),
        _os(status="Fechada Produtiva", natureza="SEM ACESSO"),
        _os(status="Cancelado", natureza="SEM ACESSO"),
        _os(natureza="SEM ACESSO", grupo="REG-LAGOA SECA"),
    ])

    resp = _buscar_dados_tempo_real("CAMPINA GRANDE")

    assert resp["abertas_agora"] == 3
    assert resp["abertas_agora_por_natureza"] == {"SEM ACESSO": 2, "CORRETIVO": 1}


def test_abertas_por_natureza_sem_natureza_vira_na(fake_client):
    """OS sem natureza entram na chave 'N/A'."""
    fake_client([
        _os(natureza="SEM ACESSO"),
        _os(natureza=None),
        _os(natureza="INSTALAÇÃO"),
    ])

    resp = _buscar_dados_tempo_real("CAMPINA GRANDE")

    assert resp["abertas_agora_por_natureza"] == {
        "SEM ACESSO": 1,
        "INSTALAÇÃO": 1,
        "N/A": 1,
    }


def test_lagoa_seca_filtra_por_sua_unidade(fake_client):
    fake_client([
        _os(natureza="SEM ACESSO", grupo="REG-LAGOA SECA"),
        _os(natureza="INSTALAÇÃO", grupo="REG-LAGOA SECA"),
        _os(natureza="SEM ACESSO", grupo="REG-CAMPINA GRANDE"),
    ])

    resp = _buscar_dados_tempo_real("LAGOA SECA")

    assert resp["abertas_agora"] == 2
    assert resp["abertas_agora_por_natureza"] == {
        "SEM ACESSO": 1,
        "INSTALAÇÃO": 1,
    }


def test_regressao_chaves_existentes(fake_client):
    """As chaves originais do endpoint continuam presentes e corretas."""
    fake_client([
        _os(natureza="SEM ACESSO", abertura=ONTEM),
        _os(status="Fechada Produtiva", natureza="CORRETIVO", abertura=ONTEM, encerramento=HOJE),
        _os(status="Fechada Improdutiva", natureza="CORRETIVO", abertura=ONTEM, encerramento=HOJE),
        _os(natureza="SEM ACESSO", sla="Vencido", responsavel=""),
    ])

    resp = _buscar_dados_tempo_real("CAMPINA GRANDE")

    assert resp["detalhe_status"] == {"Aberta Aguardando Agendamento": 2}
    assert resp["encerradas_hoje"]["produtivas"] == 1
    assert resp["encerradas_hoje"]["improdutivas"] == 1
    assert resp["encerradas_hoje"]["produtivas_por_natureza"] == {"CORRETIVO": 1}
    assert resp["abertas_hoje"]["total"] == 1
    assert resp["abertas_hoje"]["por_natureza"] == {"SEM ACESSO": 1}
    assert resp["sla_vencido"] == 1
    assert resp["sem_tecnico"] == 1
    assert resp["unidade"] == "CAMPINA GRANDE"
    assert resp["fonte"] == "Proxxima API (tempo real)"


def test_unidade_invalida_levanta_valueerror(fake_client):
    fake_client([])
    with pytest.raises(ValueError):
        _buscar_dados_tempo_real("OUTRA UNIDADE")