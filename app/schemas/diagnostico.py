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


class PontuacaoTecnicoDiaResumo(BaseModel):
    """Ponto de um dia (data + pontos) de uma equipe/técnico."""

    data: date
    pontos: float
    nao_pontua: bool = False


class PontuacaoEquipe(BaseModel):
    """Pontuação de uma equipe/técnico no dia e na semana (com metas)."""

    tecnico: str
    nao_pontua: bool = False
    pontos_dia: float = 0.0
    meta_dia: float | None  # None = fim de semana (sem meta)
    cumpre_meta_dia: bool | None = None
    ponto_semana: float
    meta_semana: float
    cumpre_meta_semana: bool
    dias: list[PontuacaoTecnicoDiaResumo]


class PontuacaoEquipeResumo(BaseModel):
    """Pontuação das equipes de uma unidade no dia e na semana.

    Fonte: webhook n8n ``aniel-aovivo`` (``fechSemana``), sincronizado em
    ``pontuacao_tecnico_dia``. Metas: 8 pontos/dia de SEG a SEX (sábado e
    domingo sem meta) e 40 pontos/semana (semana = SEG a DOM).
    """

    unidade: str
    data: date
    fonte: str
    semana_de: date
    semana_ate: date
    meta_dia: float | None
    meta_semana: float
    total_pontos_dia: float
    total_pontos_semana: float
    equipes: list[PontuacaoEquipe]


class EncerradaNatureza(BaseModel):
    """Encerradas de uma natureza no período (fechadas prod/improd + canceladas)."""

    natureza: str
    total: int
    produtivas: int
    improdutivas: int
    canceladas: int


class EncerradasPorDia(BaseModel):
    """Encerradas agrupadas por dia do período."""

    data: date
    total: int
    produtivas: int
    improdutivas: int
    canceladas: int


class EncerradasResumo(BaseModel):
    """Solicitações encerradas no período, por unidade.

    Filtra pela data de encerramento (``dataHora_Encerramento_OS`` do GetAll,
    coluna ``fechamento``). "Encerradas" = status Fechada Produtiva /
    Fechada Improdutiva (canceladas saem à parte). A taxa de produtividade é
    produtivas / (produtivas + improdutivas).
    """

    unidade: str
    periodo_de: date
    periodo_ate: date
    total_encerradas: int
    produtivas: int
    improdutivas: int
    canceladas: int
    taxa_produtiva: float | None
    por_natureza: list[EncerradaNatureza]
    por_dia: list[EncerradasPorDia]


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
