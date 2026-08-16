from datetime import date

from pydantic import BaseModel


class InspecaoResumo(BaseModel):
    data_inspecao: date | None = None
    pontuacao: float | None = None
    inspetor: str | None = None


class DiagnosticoTecnico(BaseModel):
    """Diagnóstico completo de um técnico cruzando as 3 fontes."""

    tecnico: str
    periodo_de: date
    periodo_ate: date
    recorrencia_reaberturas: int
    recorrencia_total_protocolos: int
    produtividade: dict
    he_horas: float | None = None
    infracoes: int = 0
    ultima_inspecao: InspecaoResumo | None = None
    alerta: list[str]


class StatusUnidade(BaseModel):
    """Status agregado de uma unidade (backlog + HE + recorrência)."""

    unidade: str
    abertas: int
    fechadas_produtivas: int
    fechadas_improdutivas: int
    canceladas: int
    he_horas: float | None = None
    infr_dias: int = 0
    recorrencias: int = 0


class ComparativoUnidades(BaseModel):
    periodo_de: date
    periodo_ate: date
    unidades: list[StatusUnidade]
