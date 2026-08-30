"""Checagem diária de expiração do cookie do painel-ope.

Alerta preventivo via Telegram quando faltar pouco pra expirar (<= 1 dia),
para que o usuário renove antes do sync começar a falhar.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.services.painel_ope_client import AuthenticationError, PainelOpeClient
from app.services.telegram import avisar_telegram

logger = logging.getLogger(__name__)

ALERTA_DAYS = 1


def checar_expiracao_cookie() -> None:
    """Checa expiração E validade real da sessão do painel-ope via Telegram.

    O ``exp`` do JWT pode estar no futuro mas a sessão ter sido invalidada no
    servidor (ex.: novo login do usuário invalida a anterior — caso observado
    em 2026-08-30: exp +10 dias com /analises respondendo 401). Por isso, além
    de ler o ``exp``, faz uma sonda autenticada leve (``/semanatec``) para
    detectar sessão invalidada e alertar no mesmo dia.
    """
    if not settings.ope_session_cookie:
        logger.warning("[cookie] ope_session ausente — sincronização do painel-ope inativa.")
        avisar_telegram("⚠️ Cookie do painel-ope ausente (OPE_SESSION_COOKIE vazio). Configure antes do próximo sync.")
        return

    client = PainelOpeClient()
    try:
        dias = client.dias_para_expirar()
    except AuthenticationError as exc:
        logger.error("[cookie] cookie inválido: %s", exc)
        avisar_telegram("⚠️ Cookie do painel-ope inválido. Renove em painel-ope.vercel.app.")
        return

    try:
        client.get_semanatec(setor="REG02")
    except AuthenticationError:
        avisar_telegram(
            "⚠️ Sessão do painel-ope invalidada no servidor (401), mesmo com exp "
            "válido. Faça login Novamente em painel-ope.vercel.app e renove o "
            "cookie OPE_SESSION_COOKIE."
        )
        return

    if dias <= ALERTA_DAYS:
        avisar_telegram(f"⚠️ Cookie do painel-ope expira em {dias} dia(s). Renove em painel-ope.vercel.app.")
    else:
        logger.info("[cookie] expira em %d dia(s) e sessão validada no servidor.", dias)
