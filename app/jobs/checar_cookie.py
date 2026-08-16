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
    """Se o cookie está perto de expirar, avisa via Telegram."""
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

    if dias <= ALERTA_DAYS:
        avisar_telegram(f"⚠️ Cookie do painel-ope expira em {dias} dia(s). Renove em painel-ope.vercel.app.")
    else:
        logger.info("[cookie] expira em %d dia(s).", dias)
