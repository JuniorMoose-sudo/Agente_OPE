"""Testes do PainelOpeClient — decode de cookie e expiração, sem rede."""

import base64
import json
import time
from datetime import datetime, timezone

import pytest

from app.services.painel_ope_client import (
    AuthenticationError,
    PainelOpeClient,
    _decodificar_payload_jwt,
)


def _b64url(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode()).decode().rstrip("=")


def _montar_cookie(payload: dict, assinatura: str = "sig") -> str:
    corpo = json.dumps(payload, separators=(",", ":"))
    return f"{_b64url(corpo)}.{assinatura}"


def _montar_jwt3(payload: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}))
    corpo = _b64url(json.dumps(payload, separators=(",", ":")))
    return f"{header}.{corpo}.assinatura"


class TestDecodificarPayloadJwt:
    def test_cookie_formato_real_2_segmentos(self):
        payload = {"email": "x@x", "t": 1, "exp": 1_700_000_000}
        assert _decodificar_payload_jwt(_montar_cookie(payload)) == payload

    def test_jwt_classico_3_segmentos(self):
        payload = {"sub": "u", "exp": 1_700_000_000}
        assert _decodificar_payload_jwt(_montar_jwt3(payload)) == payload

    def test_payload_invalido(self):
        with pytest.raises(AuthenticationError):
            _decodificar_payload_jwt("abc.def")

    def test_segmentos_insuficientes(self):
        with pytest.raises(AuthenticationError):
            _decodificar_payload_jwt("sosegmento")


class TestDiasParaExpirar:
    def test_cookie_futuro(self, monkeypatch):
        agora = datetime.now(timezone.utc)
        exp = int(agora.timestamp()) + 6 * 86400
        client = PainelOpeClient(cookie_session=_montar_cookie({"exp": exp}))
        assert client.dias_para_expirar() == 6

    def test_cookie_expirado(self):
        client = PainelOpeClient(cookie_session=_montar_cookie({"exp": int(time.time()) - 86400}))
        assert client.dias_para_expirar() < 0

    def test_jwt_classico_tambem_funciona(self):
        agora = datetime.now(timezone.utc)
        exp = int(agora.timestamp()) + 3 * 86400
        client = PainelOpeClient(cookie_session=_montar_jwt3({"exp": exp}))
        assert client.dias_para_expirar() == 3

    def test_sem_claim_exp(self):
        client = PainelOpeClient(cookie_session=_montar_cookie({"email": "x@x"}))
        with pytest.raises(AuthenticationError):
            client.dias_para_expirar()

    def test_cookie_vazio(self):
        with pytest.raises(AuthenticationError):
            PainelOpeClient(cookie_session="")
