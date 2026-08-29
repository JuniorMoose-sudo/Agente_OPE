"""Testes do cliente n8n (aniel-aovivo) e da soma de pontuação por técnico/dia.

Sem rede: o httpx.Client é substituído por fake. A soma ``sumarizar_pontuacao``
é função pura (fonte da pontuação diária das equipes).
"""

import pytest

from app.services.aniel_client import (
    AnielClient,
    AnielRequestError,
    sumarizar_pontuacao,
)

_PAYLOAD_VALIDO = {
    "fechSemana": [],
    "naoPontua": [],
    "tecUnidade": {},
    "matriculaTecnico": {},
    "hojeDK": "20260829",
    "semanaDK": ["20260824", "20260825"],
    "semanaDias": ["24/08"],
    "geradoEm": "29/08/2026 11:30",
    "unidades": ["CAMPINA GRANDE"],
}


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, url):
        return FakeResponse(200, _PAYLOAD_VALIDO)

    def close(self):
        pass


class TestFetchAovivo:
    def test_payload_valido_passou(self, monkeypatch):
        monkeypatch.setattr("app.services.aniel_client.httpx.Client", FakeClient)
        with AnielClient() as client:
            payload = client.fetch_aovivo()
        assert payload["hojeDK"] == "20260829"
        assert payload["fechSemana"] == []

    def test_http_nao_200_levanta_erro(self, monkeypatch):
        class Cli(FakeClient):
            def get(self, url):
                return FakeResponse(500)

        monkeypatch.setattr("app.services.aniel_client.httpx.Client", Cli)
        with AnielClient() as client:
            with pytest.raises(AnielRequestError, match="HTTP 500"):
                client.fetch_aovivo()

    def test_chaves_esperadas_ausentes_levantam_erro(self, monkeypatch):
        class Cli(FakeClient):
            def get(self, url):
                return FakeResponse(200, {"fechSemana": []})

        monkeypatch.setattr("app.services.aniel_client.httpx.Client", Cli)
        with AnielClient() as client:
            with pytest.raises(AnielRequestError, match="chaves esperadas"):
                client.fetch_aovivo()

    def test_fechsemana_nao_lista_levanta_erro(self, monkeypatch):
        class Cli(FakeClient):
            def get(self, url):
                return FakeResponse(200, {**_PAYLOAD_VALIDO, "fechSemana": {}})

        monkeypatch.setattr("app.services.aniel_client.httpx.Client", Cli)
        with AnielClient() as client:
            with pytest.raises(AnielRequestError, match="não é uma lista"):
                client.fetch_aovivo()


class TestSumarizarPontuacao:
    def test_soma_por_tecnico_unidade_e_dia(self):
        fechamentos = [
            {"os": "1/1", "tecnico": "TEC A", "uni": "CAMPINA GRANDE", "encDK": "20260824", "pontos": 2},
            {"os": "2/1", "tecnico": "TEC A", "uni": "CAMPINA GRANDE", "encDK": "20260824", "pontos": 1.33},
            {"os": "3/1", "tecnico": "TEC A", "uni": "CAMPINA GRANDE", "encDK": "20260825", "pontos": 4},
            {"os": "4/1", "tecnico": "TEC B", "uni": "LAGOA SECA", "encDK": "20260824", "pontos": 8},
        ]
        soma = sumarizar_pontuacao(fechamentos)
        assert soma == {
            ("TEC A", "CAMPINA GRANDE", "20260824"): 3.33,
            ("TEC A", "CAMPINA GRANDE", "20260825"): 4.0,
            ("TEC B", "LAGOA SECA", "20260824"): 8.0,
        }

    def test_pontos_invalidos_contam_zero(self):
        soma = sumarizar_pontuacao(
            [{"os": "1/1", "tecnico": "TEC A", "uni": "CG", "encDK": "20260824", "pontos": "abc"}]
        )
        assert soma[("TEC A", "CG", "20260824")] == 0.0

    def test_linha_sem_os_ou_sem_dia_ignorada(self):
        soma = sumarizar_pontuacao(
            [
                {"tecnico": "TEC A", "uni": "CG", "encDK": "20260824", "pontos": 5},
                {"os": "1/1", "tecnico": "TEC A", "uni": "CG", "pontos": 5},
                {"os": "2/1", "tecnico": "", "uni": "CG", "encDK": "20260824", "pontos": 5},
                "lixo",
            ]
        )
        assert soma == {("(SEM TÉCNICO)", "CG", "20260824"): 5.0}

    def test_tecnico_vazio_vira_rotulo(self):
        soma = sumarizar_pontuacao(
            [{"os": "1/1", "tecnico": None, "uni": "CG", "encDK": "20260824", "pontos": 2}]
        )
        assert soma == {("(SEM TÉCNICO)", "CG", "20260824"): 2.0}