"""Endpoints de leitura da planilha Google Sheets.

Consulta genérica: o agente pode listar abas e ler dados de qualquer aba.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.security import exigir_token_ops
from app.services.sheets_client import SheetsClient

router = APIRouter(
    prefix="/planilha",
    tags=["planilha"],
    dependencies=[Depends(exigir_token_ops)],
)

_client: SheetsClient | None = None


def _get_client() -> SheetsClient:
    global _client
    if _client is None:
        _client = SheetsClient()
    return _client


@router.get("/abas")
async def listar_abas() -> list[str]:
    """Lista todas as abas disponíveis na planilha."""
    client = _get_client()
    if not client.disponivel:
        raise HTTPException(status_code=503, detail="Planilha Google Sheets indisponível (sem credenciais ou sem acesso).")
    abas = client.listar_abas()
    return abas


@router.get("/{aba}")
async def ler_aba(
    aba: str,
    limite: int = Query(default=200, ge=1, le=2000, description="Máximo de linhas retornadas"),
) -> list[dict]:
    """Lê dados de uma aba específica. Retorna lista de registros (dicts)."""
    client = _get_client()
    if not client.disponivel:
        raise HTTPException(status_code=503, detail="Planilha Google Sheets indisponível (sem credenciais ou sem acesso).")
    dados = client.ler_aba(aba)
    if not dados:
        raise HTTPException(status_code=404, detail=f"Aba '{aba}' não encontrada ou vazia.")
    return dados[:limite]
