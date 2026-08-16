from datetime import date, datetime

from pydantic import BaseModel


class RecorrenciaPorTecnico(BaseModel):
    """Contagem de recorrência de um técnico num período (é_recorrencia = SIM)."""

    tecnico: str
    periodo_de: date
    periodo_ate: date
    total_protocolos: int
    recorrencias: int


class RecorrenciaDetalhe(BaseModel):
    protocolo: str
    unidade: str | None = None
    cidade: str | None = None
    problema_fechamento: str | None = None
    protocolo_anterior: str | None = None
    dias_entre_os: int | None = None
    data_abertura: datetime | None = None
    data_fechamento: datetime | None = None
