"""Endpoints de relatórios.

POST /relatorios — gera um relatório semanal em .docx
GET  /relatorios/{id} — metadados do relatório
GET  /relatorios/{id}/download — download do arquivo .docx
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.relatorio import Relatorio
from app.security import exigir_token_ops
from app.services.relatorio import gerar_relatorio_semanal

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


class RelatorioRequest(BaseModel):
    unidade: str
    periodo_de: str  # YYYY-MM-DD
    periodo_ate: str  # YYYY-MM-DD


class RelatorioResponse(BaseModel):
    id: int
    titulo: str
    unidade: str
    periodo_de: str
    periodo_ate: str
    nome_arquivo: str


@router.post(
    "",
    response_model=RelatorioResponse,
    dependencies=[Depends(exigir_token_ops)],
)
def criar_relatorio(body: RelatorioRequest, db: Session = Depends(get_db)):
    try:
        de = date.fromisoformat(body.periodo_de)
        ate = date.fromisoformat(body.periodo_ate)
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas no formato YYYY-MM-DD")

    if de > ate:
        raise HTTPException(status_code=400, detail="periodo_de deve ser anterior a periodo_ate")

    reg = gerar_relatorio_semanal(db, body.unidade, de, ate)
    return RelatorioResponse(
        id=reg.id,
        titulo=reg.titulo,
        unidade=reg.unidade,
        periodo_de=reg.periodo_de,
        periodo_ate=reg.periodo_ate,
        nome_arquivo=reg.nome_arquivo,
    )


@router.get(
    "/{relatorio_id}",
    response_model=RelatorioResponse,
    dependencies=[Depends(exigir_token_ops)],
)
def obter_relatorio(relatorio_id: int, db: Session = Depends(get_db)):
    reg = db.get(Relatorio, relatorio_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return RelatorioResponse(
        id=reg.id,
        titulo=reg.titulo,
        unidade=reg.unidade,
        periodo_de=reg.periodo_de,
        periodo_ate=reg.periodo_ate,
        nome_arquivo=reg.nome_arquivo,
    )


@router.get(
    "/{relatorio_id}/download",
)
def download_relatorio(relatorio_id: int, db: Session = Depends(get_db)):
    reg = db.get(Relatorio, relatorio_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    import os
    if not os.path.exists(reg.caminho):
        raise HTTPException(status_code=410, detail="Arquivo não encontrado no servidor")

    return FileResponse(
        path=reg.caminho,
        filename=reg.nome_arquivo,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
