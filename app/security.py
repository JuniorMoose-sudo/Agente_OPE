"""Segurança da própria API — token de acesso para o plugin do agente (Sprint 5).

O token é lido de `settings.ops_api_token` (OPS_API_TOKEN no .env, nunca hardcoded).
Comportamento de falha controlada:
- Token não configurado no servidor -> 503 (config ausente, não contorna).
- Header ausente ou token inválido -> 401 (não tenta contornar).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer = HTTPBearer(auto_error=False)


def exigir_token_ops(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if not settings.ops_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPS_API_TOKEN não configurado no servidor. Defina no .env para habilitar os endpoints de diagnóstico.",
        )
    if creds is None or creds.credentials != settings.ops_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de API inválido ou ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )
