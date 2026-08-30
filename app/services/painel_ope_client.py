"""Cliente do painel-ope (Vercel): banco de horas, HE e infrações.

Autenticação por cookie de sessão ``ope_session`` (JWT com claim ``exp``,
validade ~7 dias). O cookie vem sempre de ``settings.ope_session_cookie``
(variável de ambiente) — nunca é hardcoded nem impresso em log/resumo.
Os logs informam apenas se o cookie está "configurado"/"ausente" e quantos
dias faltam para expirar.

Uso típico::

    from app.services.painel_ope_client import PainelOpeClient

    client = PainelOpeClient()  # usa settings.ope_session_cookie
    try:
        analises = client.get_analises(de="20260810", ate="20260816", setor="REG02")
    finally:
        client.close()
"""

from __future__ import annotations

import base64
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://painel-ope.vercel.app/api"

COOKIE_NAME = "ope_session"

# /analises é pesado e roda em cold start no Vercel — 15s não bastava (ReadTimeout
# real em 2026-08-30 com cookie válido). Só é usado em jobs de sync, não no
# caminho de request, então um timeout maior é seguro.
HTTP_TIMEOUT = 60

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class PainelOpeError(Exception):
    """Erro base do cliente do painel-ope."""


class AuthenticationError(PainelOpeError):
    """Cookie ausente, expirado ou sessão inválida (401/403)."""


class PainelOpeRequestError(PainelOpeError):
    """Falha na comunicação com o painel-ope."""


def _decodificar_payload_jwt(cookie: str) -> dict[str, Any]:
    """Extrai o payload JSON (claims) de um cookie de sessão.

    O cookie real é ``{base64url(JSON)}.{assinatura}`` (2 segmentos); o JWT
    clássico tem 3 (header.payload.sig). Para cobrir ambos, percorre os
    segmentos e usa o primeiro que decodificar como JSON. Não valida
    assinatura — apenas para ler a expiração. Nunca retorna nem registra
    o token.
    """
    segmentos = cookie.split(".")
    if len(segmentos) < 2:
        raise AuthenticationError(
            "Cookie do painel-ope não está no formato esperado (segmentos insuficientes)."
        )

    dicts: list[dict[str, Any]] = []
    for segmento in segmentos:
        payload_b64 = segmento + "=" * (-len(segmento) % 4)
        try:
            dados = json.loads(base64.urlsafe_b64decode(payload_b64))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(dados, dict):
            dicts.append(dados)

    # No JWT clássico (3 segmentos) o primeiro dict é o header; preferimos
    # sempre o segmento que carrega o claim ``exp``, quando existir.
    for dados in dicts:
        if "exp" in dados:
            return dados
    if dicts:
        return dicts[0]

    raise AuthenticationError("Cookie do painel-ope não contém um payload JSON válido.")


class PainelOpeClient:
    """Cliente síncrono do painel-ope (httpx), com checagem de expiração."""

    def __init__(self, cookie_session: str | None = None) -> None:
        cookie = cookie_session if cookie_session is not None else settings.ope_session_cookie
        if not cookie:
            raise AuthenticationError(
                "Cookie do painel-ope não configurado (OPE_SESSION_COOKIE ausente no .env)."
            )
        self.cookie = cookie
        self.headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Cookie": f"{COOKIE_NAME}={cookie}",
        }
        self.client = httpx.Client(timeout=HTTP_TIMEOUT, headers=self.headers)

    def dias_para_expirar(self) -> int:
        """Dias até o ``exp`` do JWT (negativo se já expirou), arredondado p/ cima."""
        payload = _decodificar_payload_jwt(self.cookie)
        exp = payload.get("exp")
        if exp is None:
            raise AuthenticationError("JWT do painel-ope sem claim 'exp'.")
        exp_dt = datetime.fromtimestamp(float(exp), tz=timezone.utc)
        segundos = (exp_dt - datetime.now(timezone.utc)).total_seconds()
        return math.ceil(segundos / 86400)

    def get_analises(self, *, de: str, ate: str, setor: str) -> dict[str, Any]:
        """Chama POST /api/analises e devolve o payload JSON."""
        return self._post("/analises", {"de": de, "ate": ate, "setor": setor})

    def get_semanatec(self, *, setor: str) -> dict[str, Any]:
        """Chama POST /api/semanatec e devolve o payload JSON."""
        return self._post("/semanatec", {"setor": setor})

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.post(f"{BASE_URL}{path}", json=body)
        except httpx.HTTPError as exc:
            raise PainelOpeRequestError(f"Falha ao chamar {path}: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"{path} respondeu HTTP {response.status_code}: sessão inválida "
                "ou cookie expirado. Renove o cookie do painel-ope."
            )

        if response.status_code != 200:
            raise PainelOpeRequestError(f"{path} respondeu HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise PainelOpeRequestError(f"Resposta de {path} não é JSON válido.") from exc

        if not isinstance(payload, dict):
            raise PainelOpeRequestError(f"Resposta de {path} não é um objeto JSON.")
        return payload

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> PainelOpeClient:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
