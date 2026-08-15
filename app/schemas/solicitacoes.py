from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SolicitacaoResumo(BaseModel):
    unidade: str
    total: int
    abertas: int
    fechadas_produtivas: int
    fechadas_improdutivas: int
    canceladas: int


class SolicitacaoDetalhe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    os: str
    unidade: str | None
    natureza: str | None
    status: str | None
    abertura: datetime | None
    venc: datetime | None
    sla_status: str | None


class SolicitacoesPorTecnico(BaseModel):
    tecnico: str
    total: int
    abertas: int
    detalhe: list[SolicitacaoDetalhe]
