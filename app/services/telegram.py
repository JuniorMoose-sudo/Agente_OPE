"""Envio de alertas via Telegram (bot).

Sem token/chat configurados, apenas loga warning e segue — o sistema nunca
falha por falta de alerta.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_URL = "https://api.telegram.org/bot{token}/sendMessage"


def avisar_telegram(mensagem: str) -> bool:
    """Envia mensagem via bot do Telegram. Retorna True se enviada."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("[telegram] sem token/chat configurados — mensagem não enviada: %s", mensagem)
        return False

    try:
        resp = httpx.post(
            _URL.format(token=settings.telegram_bot_token),
            json={"chat_id": settings.telegram_chat_id, "text": mensagem},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("[telegram] alerta enviado: %s", mensagem)
        return True
    except httpx.HTTPError as exc:
        logger.error("[telegram] falha ao enviar alerta: %s", exc)
        return False
