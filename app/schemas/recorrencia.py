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


class RankingItem(BaseModel):
    """Um técnico no ranking de recorrências (é_recorrencia = SIM)."""

    tecnico: str
    recorrencias: int
    os_no_analitico: int
    taxa: float


class RankingRecorrencia(BaseModel):
    """Ranking de técnicos com mais recorrências de uma unidade no período."""

    unidade: str
    periodo_de: date
    periodo_ate: date
    top: int
    total_recorrencias: int
    ranking: list[RankingItem]


class ProblemaItem(BaseModel):
    """Contagem de recorrência de uma causa (Problema do fechamento)."""

    problema: str
    recorrencias: int
    pct: float


class ResumoCategoria(BaseModel):
    """Resumo de uma categoria macro (culpa do campo, rede externa, administrativo)."""

    recorrencias: int
    pct: float


class RecorrenciaPorProblema(BaseModel):
    """Recorrências de uma unidade no período quebradas por problema (causa)."""

    unidade: str
    periodo_de: date
    periodo_ate: date
    total_recorrencias: int
    por_problema: list[ProblemaItem]
    resumo_categorias: dict[str, ResumoCategoria]
