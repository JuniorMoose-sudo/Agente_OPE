from datetime import date

from pydantic import BaseModel


class InspecaoResumo(BaseModel):
    data_inspecao: date | None = None
    pontuacao: float | None = None
    inspetor: str | None = None


class PontuacaoTotvsResumo(BaseModel):
    """Resumo da pontuação TOTVS (GoodData) de um técnico no período."""

    pontuacao_media: float
    pontuacao_total: float
    dias_com_dados: int
    detalhes: list[dict]


class AgendadoNatureza(BaseModel):
    """Total de atendimentos agendados de uma natureza em um dia."""

    natureza: str | None
    total: int
    com_equipe: int


class AgendadosResumo(BaseModel):
    """Atendimentos agendados para uma data, por unidade e natureza.

    Com base em ``data_Hora_Agendamento_OS`` do GetAll (Proxxima). "Com equipe"
    significa que a OS já tem técnico responsável ou equipe atribuída.
    """

    unidade: str
    data: date
    total: int
    com_equipe: int
    sem_equipe: int
    por_natureza: list[AgendadoNatureza]


class DiagnosticoTecnico(BaseModel):
    """Diagnóstico completo de um técnico cruzando as 3 fontes."""

    tecnico: str
    periodo_de: date
    periodo_ate: date
    recorrencia_reaberturas: int
    recorrencia_os_no_analitico: int
    recorrencia_contexto: str
    produtividade: dict
    he_horas: float | None = None
    infracoes: int = 0
    ultima_inspecao: InspecaoResumo | None = None
    pontuacao_totvs: PontuacaoTotvsResumo | None = None
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
