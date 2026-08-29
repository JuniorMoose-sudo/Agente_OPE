"""Testes do cliente do painel Operações (recorrência analítica via cookie)."""

import pytest

from app.config import settings
from app.services import operacoes_client
from app.services.operacoes_client import (
    OperacoesAuthError,
    OperacoesClient,
    OperacoesRequestError,
)

XLSX_BYTES = b"PK\x03\x04algum-conteudo"


class _FakeResponse:
    def __init__(self, content=b"", status_code=200, url="", history=None, headers=None):
        self.content = content
        self.status_code = status_code
        self.url = url
        self.history = history or []
        self.headers = headers or {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class _FakeHttpClient:
    def __init__(self, response):
        self._response = response
        self.get_kwargs = None

    def get(self, url, **kwargs):
        self.get_kwargs = (url, kwargs)
        return self._response

    def close(self):
        pass


@pytest.fixture
def sem_cookie(monkeypatch):
    monkeypatch.setattr(settings, "operacoes_session_cookie", None)


@pytest.fixture
def com_cookie(monkeypatch):
    monkeypatch.setattr(settings, "operacoes_session_cookie", "segredo-de-teste")


def test_sem_cookie_nao_configurado(sem_cookie):
    with pytest.raises(OperacoesAuthError, match="não configurado"):
        OperacoesClient()


def test_fetch_analitico_ok(com_cookie, monkeypatch):
    resp = _FakeResponse(content=XLSX_BYTES, url="https://operacoes.proxxima.net/painel/recorrencia/analitico")
    fake = _FakeHttpClient(resp)
    monkeypatch.setattr(operacoes_client.httpx, "Client", lambda *a, **k: fake)

    client = OperacoesClient("segredo-de-teste")
    try:
        b = client.fetch_analitico("UNIDADE CAMPINA GRANDE", "2026-08")
    finally:
        client.close()

    assert b == XLSX_BYTES
    url, _ = fake.get_kwargs
    assert "mes=2026-08" in url
    assert "unidade=UNIDADE+CAMPINA+GRANDE" in url


def test_fetch_analitico_encoded_lagoa_seca(com_cookie, monkeypatch):
    resp = _FakeResponse(content=XLSX_BYTES, url="https://operacoes.proxxima.net/painel/recorrencia/analitico")
    fake = _FakeHttpClient(resp)
    monkeypatch.setattr(operacoes_client.httpx, "Client", lambda *a, **k: fake)

    client = OperacoesClient("x")
    try:
        client.fetch_analitico("UNIDADE LAGOA SECA", "2026-07")
    finally:
        client.close()

    url, _ = fake.get_kwargs
    assert "unidade=UNIDADE+LAGOA+SECA" in url


def test_fetch_analitico_redireciona_login_levanta_auth(com_cookie, monkeypatch):
    hop = _FakeResponse(status_code=303, headers={"location": "/login"})
    resp = _FakeResponse(
        content=b"<html>login</html>",
        url="https://operacoes.proxxima.net/login",
        history=[hop],
    )
    fake = _FakeHttpClient(resp)
    monkeypatch.setattr(operacoes_client.httpx, "Client", lambda *a, **k: fake)

    client = OperacoesClient("x")
    try:
        with pytest.raises(OperacoesAuthError, match="expirada"):
            client.fetch_analitico("UNIDADE CAMPINA GRANDE", "2026-08")
    finally:
        client.close()


def test_fetch_analitico_html_sem_redirect_levanta_request_error(com_cookie, monkeypatch):
    resp = _FakeResponse(
        content=b"<html>pagina de erro</html>",
        url="https://operacoes.proxxima.net/painel/recorrencia/analitico",
        headers={"content-type": "text/html; charset=utf-8"},
    )
    fake = _FakeHttpClient(resp)
    monkeypatch.setattr(operacoes_client.httpx, "Client", lambda *a, **k: fake)

    client = OperacoesClient("x")
    try:
        with pytest.raises(OperacoesRequestError, match="não é um xlsx"):
            client.fetch_analitico("UNIDADE CAMPINA GRANDE", "2026-08")
    finally:
        client.close()


def test_http_status_diferente_de_200_levanta_request_error(com_cookie, monkeypatch):
    resp = _FakeResponse(content=b"", status_code=500, url="https://operacoes.proxxima.net/painel/recorrencia/analitico")
    fake = _FakeHttpClient(resp)
    monkeypatch.setattr(operacoes_client.httpx, "Client", lambda *a, **k: fake)

    client = OperacoesClient("x")
    try:
        with pytest.raises(OperacoesRequestError, match="HTTP 500"):
            client.fetch_analitico("UNIDADE CAMPINA GRANDE", "2026-08")
    finally:
        client.close()