"""Cliente do painel Operações (operacoes.proxxima.net): recorrência analítica.

O painel é server-rendered e autentica por **Zoho SSO** — não há usuário/senha
de API; o acesso programático usa o cookie de sessão ``bl_session`` (mesmo
padrão do painel-ope). O cookie vem sempre de ``settings.operacoes_session_cookie``
— nunca hardcoded nem impresso em log/resumo.

O endpoint ``/painel/recorrencia/analitico?mes=YYYY-MM&unidade=UNIDADE X`` baixa
exatamente o Excel "Analítico" do export manual (aba ``Analitico``), que o
``app.etl.recorrencia.importar_recorrencia`` já sabe ler. Objetivo: substituir o
passo manual pela sincronização programática.

Uso típico::

    from app.services.operacoes_client import OperacoesClient

    client = OperacoesClient()
    try:
        conteudo = client.fetch_analitico("UNIDADE CAMPINA GRANDE", "2026-08")
    finally:
        client.close()
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://operacoes.proxxima.net"
LOGIN_PATH = "/login"
ANALITICO_PATH = "/painel/recorrencia/analitico"

COOKIE_NAME = "bl_session"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

MAGIC_XLSX = b"PK"

# Unidades atendidas pelo agente (nomes exatos usados no parâmetro `unidade`).
UNIDADES_RECORRENCIA = (
    "UNIDADE CAMPINA GRANDE",
    "UNIDADE LAGOA SECA",
)


def _encode_unidade(unidade: str) -> str:
    """Codifica o nome conforme o painel (form-urlencoded, espaço vira '+')."""
    return quote(unidade, safe="").replace("%20", "+")


class OperacoesError(Exception):
    """Erro base do cliente do painel Operações."""


class OperacoesAuthError(OperacoesError):
    """Cookie ausente, expirado ou sessão inválida (redirecionou para /login)."""


class OperacoesRequestError(OperacoesError):
    """Falha na comunicação ou resposta fora do esperado."""


class OperacoesClient:
    """Cliente síncrono do painel Operações (httpx), autenticado por cookie."""

    def __init__(self, cookie_session: str | None = None) -> None:
        cookie = (
            cookie_session if cookie_session is not None else settings.operacoes_session_cookie
        )
        if not cookie:
            raise OperacoesAuthError(
                "Cookie do painel Operações não configurado "
                "(OPERACOES_SESSION_COOKIE ausente no .env)."
            )
        self.cookie = cookie
        self.headers = {
            "User-Agent": USER_AGENT,
            "Cookie": f"{COOKIE_NAME}={cookie}",
        }
        self.client = httpx.Client(timeout=40, headers=self.headers)

    def fetch_analitico(self, unidade: str, mes: str) -> bytes:
        """Baixa o analítico de recorrência (xlsx) de uma unidade num mês.

        Retorna os bytes do arquivo. Levanta ``OperacoesAuthError`` quando a
        sessão está expirada (redireciona para /login) e
        ``OperacoesRequestError`` para falhas de comunicação/conteúdo.
        """
        url = f"{BASE_URL}{ANALITICO_PATH}?mes={mes}&unidade={_encode_unidade(unidade)}"
        try:
            response = self.client.get(url, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise OperacoesRequestError(f"Falha ao baixar analítico {unidade}/{mes}: {exc}") from exc

        if self._foi_para_login(response):
            raise OperacoesAuthError(
                "Sessão do painel Operações expirada (redirecionou para /login). "
                "Renove o OPERACOES_SESSION_COOKIE."
            )

        if response.status_code != 200:
            raise OperacoesRequestError(
                f"Analítico {unidade}/{mes} respondeu HTTP {response.status_code}."
            )

        conteudo = response.content
        if not conteudo.startswith(MAGIC_XLSX):
            ct = response.headers.get("content-type", "")
            raise OperacoesRequestError(
                f"Analítico {unidade}/{mes} não é um xlsx (content-type={ct}, bytes={len(conteudo)})."
            )
        return conteudo

    @staticmethod
    def _foi_para_login(response: httpx.Response) -> bool:
        """True se a sessão foi redirecionada para a página de login."""
        for hop in response.history:
            if hop.status_code in (301, 302, 303, 307, 308) and (
                hop.headers.get("location", "").endswith(LOGIN_PATH)
            ):
                return True
        return str(response.url).endswith(LOGIN_PATH)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> OperacoesClient:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()