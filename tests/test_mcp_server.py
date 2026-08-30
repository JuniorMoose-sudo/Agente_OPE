"""Testes do servidor MCP (Fase 1 do sprint Hermes).

Cobre: registro das 5 ferramentas, cálculo da semana atual (default), mapeamento
de argumentos → URL/corpo, header de autorização e erros de comunicação
(401/403/503/5xx). A camada MCP é só um orquestrador do backend local — nenhuma
API externa é chamada daqui (separação sync/serve).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx
import pytest

from app.services import mcp_server
from app.services.mcp_server import (
    APIError,
    _chamar_api,
    _query,
    _semana_atual,
)

SEGUNDA = "2026-08-24"
DOMINGO = "2026-08-30"


@pytest.fixture
def sexta_28_ago(monkeypatch):
    """Congela datetime.now() numa sexta-feira (2026-08-28)."""

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 28, 10, 0, 0)

    monkeypatch.setattr(mcp_server, "datetime", FakeDatetime)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"erro {self.status_code}",
                request=httpx.Request("GET", "http://backend"),
                response=self,
            )

    def json(self):
        return self._payload


class FakeClient:
    """Substitui httpx.Client e grava a última chamada."""

    ultima: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, path, headers=None, json=None):
        FakeClient.ultima = {
            "method": method,
            "path": path,
            "headers": headers,
            "json": json,
        }
        return FakeResponse(200, {"ok": True})


class TestFerramentasRegistradas:
    def test_dez_ferramentas(self):
        tools = asyncio.run(mcp_server.mcp.list_tools())
        nomes = {t.name for t in tools}
        assert nomes == {
            "get_diagnostico_tecnico",
            "get_status_unidade",
            "get_tempo_real",
            "get_planilha",
            "get_relatorio_semanal",
            "get_ranking_recorrencia",
            "get_recorrencia_por_problema",
            "get_atendimentos_agendados",
            "get_pontuacao_equipe",
            "get_encerradas_periodo",
            "get_banco_horas_saldo",
        }

    def test_call_tool_via_fastmcp(self, monkeypatch):
        def fake_chamar(method, path, body=None):
            return json.dumps({"method": method, "path": path})

        monkeypatch.setattr(mcp_server, "_chamar_api", fake_chamar)
        res = asyncio.run(
            mcp_server.mcp.call_tool("get_tempo_real", {"unidade": "CAMPINA GRANDE"})
        )
        assert res.is_error is False
        texto = res.structured_content["result"]
        assert "/diagnostico/tempo-real/CAMPINA%20GRANDE" in texto


class TestSemanaAtual:
    def test_segunda_a_domingo(self, sexta_28_ago):
        assert _semana_atual() == (SEGUNDA, DOMINGO)

    def test_query_sem_datas_usa_semana_atual(self, sexta_28_ago):
        assert _query(None, None) == (
            f"?periodo_de={SEGUNDA}&periodo_ate={DOMINGO}"
        )

    def test_query_com_datas_explicitas(self):
        assert _query("2026-08-10", "2026-08-16") == (
            "?periodo_de=2026-08-10&periodo_ate=2026-08-16"
        )


class TestMapeamentoUrls:
    @pytest.fixture(autouse=True)
    def captura_chamadas(self, monkeypatch):
        self.capturado = {}

        def fake_chamar(method, path, body=None):
            self.capturado = {"method": method, "path": path, "body": body}
            return json.dumps({"path": path})

        monkeypatch.setattr(mcp_server, "_chamar_api", fake_chamar)

    def test_status_unidade(self):
        saida = mcp_server.get_status_unidade("CAMPINA GRANDE", "2026-08-10", "2026-08-16")
        assert self.capturado["method"] == "GET"
        assert self.capturado["path"] == (
            "/diagnostico/status-unidade/CAMPINA%20GRANDE"
            "?periodo_de=2026-08-10&periodo_ate=2026-08-16"
        )
        assert json.loads(saida)["path"] == self.capturado["path"]

    def test_diagnostico_tecnico(self, sexta_28_ago):
        mcp_server.get_diagnostico_tecnico(
            "ALVARO CORREIA DE SOUSA NETO", None, None
        )
        assert self.capturado["path"] == (
            "/diagnostico/tecnico/ALVARO%20CORREIA%20DE%20SOUSA%20NETO"
            f"?periodo_de={SEGUNDA}&periodo_ate={DOMINGO}"
        )

    def test_tempo_real(self):
        mcp_server.get_tempo_real("LAGOA SECA")
        assert self.capturado["path"] == "/diagnostico/tempo-real/LAGOA%20SECA"

    def test_ranking_recorrencia(self):
        mcp_server.get_ranking_recorrencia("CAMPINA GRANDE", "2026-08-10", "2026-08-16")
        assert self.capturado["path"] == (
            "/recorrencia/ranking?unidade=CAMPINA%20GRANDE"
            "&periodo_de=2026-08-10&periodo_ate=2026-08-16&top=5"
        )

    def test_ranking_recorrencia_top_personalizado(self):
        mcp_server.get_ranking_recorrencia("LAGOA SECA", "2026-08-10", "2026-08-16", top=10)
        assert self.capturado["path"] == (
            "/recorrencia/ranking?unidade=LAGOA%20SECA"
            "&periodo_de=2026-08-10&periodo_ate=2026-08-16&top=10"
        )

    def test_recorrencia_por_problema(self):
        mcp_server.get_recorrencia_por_problema("CAMPINA GRANDE", "2026-08-10", "2026-08-16")
        assert self.capturado["path"] == (
            "/recorrencia/por-problema?unidade=CAMPINA%20GRANDE"
            "&periodo_de=2026-08-10&periodo_ate=2026-08-16"
        )

    def test_atendimentos_agendados_explicita(self):
        mcp_server.get_atendimentos_agendados("CAMPINA GRANDE", "2026-08-29")
        assert self.capturado["path"] == (
            "/diagnostico/agendados/CAMPINA%20GRANDE?data=2026-08-29"
        )

    def test_atendimentos_agendados_padrao_amanha(self, sexta_28_ago):
        mcp_server.get_atendimentos_agendados("LAGOA SECA")
        assert self.capturado["path"] == (
            "/diagnostico/agendados/LAGOA%20SECA?data=2026-08-29"
        )

    def test_pontuacao_equipe_explicita(self):
        mcp_server.get_pontuacao_equipe("CAMPINA GRANDE", "2026-08-29")
        assert self.capturado["path"] == (
            "/diagnostico/pontuacao/CAMPINA%20GRANDE?data=2026-08-29&resumo=true"
        )

    def test_pontuacao_equipe_padrao_sem_data(self):
        mcp_server.get_pontuacao_equipe("LAGOA SECA")
        assert self.capturado["path"] == (
            "/diagnostico/pontuacao/LAGOA%20SECA?resumo=true"
        )

    def test_pontuacao_equipe_com_detalhe(self):
        mcp_server.get_pontuacao_equipe("CAMPINA GRANDE", "2026-08-29", resumo=False)
        assert self.capturado["path"] == (
            "/diagnostico/pontuacao/CAMPINA%20GRANDE?data=2026-08-29&resumo=false"
        )

    def test_encerradas_periodo_explicita(self):
        mcp_server.get_encerradas_periodo("CAMPINA GRANDE", "2026-08-24", "2026-08-30")
        assert self.capturado["path"] == (
            "/diagnostico/encerradas/CAMPINA%20GRANDE"
            "?periodo_de=2026-08-24&periodo_ate=2026-08-30"
        )

    def test_encerradas_periodo_padrao_semana(self, sexta_28_ago):
        mcp_server.get_encerradas_periodo("LAGOA SECA")
        assert self.capturado["path"] == (
            f"/diagnostico/encerradas/LAGOA%20SECA"
            f"?periodo_de={SEGUNDA}&periodo_ate={DOMINGO}"
        )

    def test_planilha_sem_aba(self):
        mcp_server.get_planilha()
        assert self.capturado["path"] == "/planilha/abas"

    def test_planilha_com_aba_e_limite(self):
        mcp_server.get_planilha("ESCALA SETEMBRO", 300)
        assert self.capturado["path"] == "/planilha/ESCALA%20SETEMBRO?limite=300"

    def test_planilha_com_aba_sem_limite(self):
        mcp_server.get_planilha("BASE")
        assert self.capturado["path"] == "/planilha/BASE"

    def test_relatorio_adiciona_download_url(self, monkeypatch):
        def fake_chamar(method, path, body=None):
            return json.dumps({"id": 7, "titulo": "rel"})

        monkeypatch.setattr(mcp_server, "_chamar_api", fake_chamar)
        saida = json.loads(
            mcp_server.get_relatorio_semanal("CAMPINA GRANDE", "2026-08-10", "2026-08-16")
        )
        assert saida["download_url"] == (
            f"{mcp_server.API_BASE}/relatorios/7/download"
        )


class TestChamarApi:
    def test_200_retorna_json(self, monkeypatch):
        monkeypatch.setattr(mcp_server.httpx, "Client", FakeClient)
        saida = _chamar_api("GET", "/x")
        assert json.loads(saida) == {"ok": True}

    def test_envia_token_bearer(self, monkeypatch):
        monkeypatch.setattr(mcp_server.httpx, "Client", FakeClient)
        monkeypatch.setattr(mcp_server, "API_TOKEN", "abc123")
        _chamar_api("GET", "/x")
        assert FakeClient.ultima["headers"] == {
            "Authorization": "Bearer abc123"
        }

    def test_sem_token_nao_envia_header(self, monkeypatch):
        monkeypatch.setattr(mcp_server.httpx, "Client", FakeClient)
        monkeypatch.setattr(mcp_server, "API_TOKEN", "")
        _chamar_api("GET", "/x")
        assert FakeClient.ultima["headers"] == {}

    @pytest.mark.parametrize("status", [401, 403], ids=["401", "403"])
    def test_token_rejeitado(self, monkeypatch, status):
        class Cli(FakeClient):
            def request(self, *a, **k):
                return FakeResponse(status)

        monkeypatch.setattr(mcp_server.httpx, "Client", Cli)
        with pytest.raises(APIError, match="rejeitou o token"):
            _chamar_api("GET", "/x")

    def test_servidor_sem_token(self, monkeypatch):
        class Cli(FakeClient):
            def request(self, *a, **k):
                return FakeResponse(503)

        monkeypatch.setattr(mcp_server.httpx, "Client", Cli)
        with pytest.raises(APIError, match="sem OPS_API_TOKEN"):
            _chamar_api("GET", "/x")

    def test_erro_5xx_propaga(self, monkeypatch):
        class Cli(FakeClient):
            def request(self, *a, **k):
                return FakeResponse(500)

        monkeypatch.setattr(mcp_server.httpx, "Client", Cli)
        with pytest.raises(httpx.HTTPStatusError):
            _chamar_api("GET", "/x")