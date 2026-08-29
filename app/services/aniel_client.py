"""Cliente do painel n8n da Proxxima (n8n.proxxima.net) — webhooks públicos.

Usado para a pontuação das equipes: o webhook ``/webhook/aniel-aovivo`` devolve
o "painel ao vivo" com ``fechSemana`` — fechamentos da semana, cada um com
``os``, ``tecnico``, ``uni`` (unidade), ``encDK`` (dia em YYYYMMDD) e ``pontos``.
A pontuação diária de uma equipe/técnico é a soma dos ``pontos`` dos dias.

Sem autenticação (GET público). O payload é grande (~4 MB) e muda de estrutura
sem aviso — os campos esperados são validados explicitamente e o número de
registros processados é logado (ver AGENTS.md: parsers externos são o ponto
mais frágil do sistema).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://n8n.proxxima.net"

CHAVES_ESPERADAS = {
    "fechSemana",
    "naoPontua",
    "tecUnidade",
    "matriculaTecnico",
    "hojeDK",
    "semanaDK",
    "semanaDias",
    "geradoEm",
    "unidades",
}


class AnielRequestError(RuntimeError):
    """Falha na comunicação com o webhook do n8n."""


class AnielClient:
    """Client síncrono do webhook ``aniel-aovivo``."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 60.0) -> None:
        self.base_url = base_url
        self.client = httpx.Client(timeout=timeout)

    def fetch_aovivo(self) -> dict[str, Any]:
        """Baixa o payload ao vivo e valida as chaves esperadas."""
        url = f"{self.base_url}/webhook/aniel-aovivo"
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            raise AnielRequestError(f"Falha ao chamar {url}: {exc}") from exc

        if response.status_code != 200:
            raise AnielRequestError(f"{url} respondeu HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise AnielRequestError(f"Resposta de {url} não é JSON válido.") from exc

        if not isinstance(payload, dict):
            raise AnielRequestError(f"Resposta de {url} não é um objeto JSON.")
        falhas = [c for c in CHAVES_ESPERADAS if c not in payload]
        if falhas:
            raise AnielRequestError(
                f"Payload do n8n sem chaves esperadas: {falhas}. "
                "O webhook aniel-aovivo mudou de estrutura?"
            )
        fechamentos = payload.get("fechSemana")
        if not isinstance(fechamentos, list):
            raise AnielRequestError("fechSemana do n8n não é uma lista.")

        itens_validos = 0
        for f in fechamentos:
            if isinstance(f, dict) and f.get("os"):
                itens_validos += 1
        logger.info(
            "[aniel] aovivo: %d registros em fechSemana (%d com os), gerado em %s",
            len(fechamentos),
            itens_validos,
            payload.get("geradoEm"),
        )
        return payload

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> AnielClient:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def sumarizar_pontuacao(fechamentos: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    """Soma ``pontos`` por (tecnico, unidade, dia YYYYMMDD) em fechSemana.

    Função pura (testável sem banco): a pontuação do dia da equipe é a soma
    dos pontos dos fechamentos daquele dia (encDK). Ignora linhas sem os ou
    sem encDK.
    """
    soma: dict[tuple[str, str, str], float] = {}
    for f in fechamentos:
        if not isinstance(f, dict):
            continue
        os_ = f.get("os")
        enc_dk = f.get("encDK")
        if not os_ or not enc_dk:
            continue
        tecnico = str(f.get("tecnico") or "").strip()
        if not tecnico:
            tecnico = "(SEM TÉCNICO)"
        unidade = str(f.get("uni") or "").strip() or "(SEM UNIDADE)"
        try:
            pontos = float(f.get("pontos", 0) or 0)
        except (TypeError, ValueError):
            pontos = 0.0
        chave = (tecnico, unidade, str(enc_dk))
        soma[chave] = soma.get(chave, 0.0) + pontos
    return soma