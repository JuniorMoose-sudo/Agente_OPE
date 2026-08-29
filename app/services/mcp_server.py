"""Servidor MCP "agente-ope" — expõe as ferramentas operacionais do backend.

O Hermes Agent (ou qualquer cliente MCP) conecta neste servidor via stdio e
ganha as mesmas ferramentas que o plugin do opencode oferece, sem precisar
falar com as APIs externas (Proxxima, painel-ope, Sheets, TOTVS) — isso
continua sendo responsabilidade do backend FastAPI (separação sync/serve).

O servidor é apenas um orquestrador: monta a URL/corpo e chama o backend
local com `Authorization: Bearer <OPS_API_TOKEN>`.

Uso:
    python -m app.services.mcp_server

Variáveis de ambiente:
    OPS_API_URL    base do backend (default http://localhost:8100)
    OPS_API_TOKEN  token Bearer (default: settings.ops_api_token do .env)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import httpx
from fastmcp import FastMCP

from app.config import settings

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("OPS_API_URL", "http://localhost:8100")
API_TOKEN = os.environ.get("OPS_API_TOKEN") or settings.ops_api_token or ""

mcp = FastMCP("agente-ope")


class APIError(RuntimeError):
    """Erro de comunicação com o backend (autenticação ou HTTP)."""


def _semana_atual() -> tuple[str, str]:
    """Segunda–domingo da semana atual, em YYYY-MM-DD (mesmo default do plugin)."""
    hoje = datetime.now()
    segunda = hoje - timedelta(days=hoje.weekday())
    domingo = segunda + timedelta(days=6)
    return segunda.strftime("%Y-%m-%d"), domingo.strftime("%Y-%m-%d")


def _query(periodo_de: Optional[str], periodo_ate: Optional[str]) -> str:
    de, ate = _semana_atual()
    return f"?periodo_de={quote(periodo_de or de)}&periodo_ate={quote(periodo_ate or ate)}"


def _chamar_api(method: str, path: str, body: Optional[dict] = None) -> str:
    """Chama o backend local e devolve o JSON como string legível.

    Injectable p/ testes: a função usa `httpx.Client`, que os testes
    substituem por um fake via monkeypatch.
    """
    headers: dict[str, str] = {}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    with httpx.Client(base_url=API_BASE, timeout=60.0) as client:
        resp = client.request(method, path, headers=headers, json=body)
    if resp.status_code in (401, 403):
        raise APIError(
            f"API rejeitou o token em {path} ({resp.status_code}) — confira OPS_API_TOKEN"
        )
    if resp.status_code == 503:
        raise APIError(
            f"API sem OPS_API_TOKEN configurado no servidor ({resp.status_code})"
        )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2, default=str)


@mcp.tool()
def get_diagnostico_tecnico(
    nome_tecnico: str,
    periodo_de: Optional[str] = None,
    periodo_ate: Optional[str] = None,
) -> str:
    """Diagnóstico completo de um técnico cruzando as 3 fontes: recorrência,
    produtividade, HE, infrações e última inspeção, com alertas. Use quando a
    pergunta for sobre um técnico específico.

    Args:
        nome_tecnico: Nome completo do técnico em MAIÚSCULAS (ex.: ALVARO CORREIA DE SOUSA NETO).
        periodo_de: Início do período (YYYY-MM-DD). Se omitido, usa a semana atual.
        periodo_ate: Fim do período (YYYY-MM-DD). Se omitido, usa a semana atual.
    """
    path = f"/diagnostico/tecnico/{quote(nome_tecnico, safe='')}{_query(periodo_de, periodo_ate)}"
    return _chamar_api("GET", path)


@mcp.tool()
def get_status_unidade(
    unidade: str,
    periodo_de: Optional[str] = None,
    periodo_ate: Optional[str] = None,
) -> str:
    """Status agregado de uma unidade: backlog (abertas), fechadas
    produtivas/improdutivas, canceladas, HE e recorrências. Use para perguntas
    do tipo 'como está Campina Grande / Lagoa Seca'.

    Args:
        unidade: Unidade: CAMPINA GRANDE ou LAGOA SECA.
        periodo_de: Início do período (YYYY-MM-DD). Se omitido, usa a semana atual.
        periodo_ate: Fim do período (YYYY-MM-DD). Se omitido, usa a semana atual.
    """
    path = f"/diagnostico/status-unidade/{quote(unidade, safe='')}{_query(periodo_de, periodo_ate)}"
    return _chamar_api("GET", path)


@mcp.tool()
def get_recorrencia_por_problema(
    unidade: str,
    periodo_de: Optional[str] = None,
    periodo_ate: Optional[str] = None,
) -> str:
    """Recorrências (é_recorrencia=SIM) de uma unidade quebradas por causa
    ("Problema do fechamento"), com resumo em 3 categorias macro.
    Sem HAR e sem lista de técnicos: tudo vem do Postgres.

    Args:
        unidade: Unidade: CAMPINA GRANDE ou LAGOA SECA.
        periodo_de: Início do período (YYYY-MM-DD). Se omitido, usa a semana atual.
        periodo_ate: Fim do período (YYYY-MM-DD). Se omitido, usa a semana atual.
    """
    de, ate = _semana_atual()
    params = (
        f"unidade={quote(unidade, safe='')}"
        f"&periodo_de={quote(periodo_de or de)}"
        f"&periodo_ate={quote(periodo_ate or ate)}"
    )
    return _chamar_api("GET", f"/recorrencia/por-problema?{params}")


@mcp.tool()
def get_ranking_recorrencia(
    unidade: str,
    periodo_de: Optional[str] = None,
    periodo_ate: Optional[str] = None,
    top: int = 5,
) -> str:
    """Ranking pronto de técnicos com mais recorrências (é_recorrencia=SIM) de
    uma unidade no período — não precisa saber a lista de técnicos antes.
    O campo `recorrencias` é o número de recorrências; `os_no_analitico` são
    todas as OS do técnico no analítico (inclui as não-recorrentes, só contexto).

    Args:
        unidade: Unidade: CAMPINA GRANDE ou LAGOA SECA.
        periodo_de: Início do período (YYYY-MM-DD). Se omitido, usa a semana atual.
        periodo_ate: Fim do período (YYYY-MM-DD). Se omitido, usa a semana atual.
        top: Quantos técnicos no ranking (padrão 5, máx 20).
    """
    de, ate = _semana_atual()
    params = (
        f"unidade={quote(unidade, safe='')}"
        f"&periodo_de={quote(periodo_de or de)}"
        f"&periodo_ate={quote(periodo_ate or ate)}"
        f"&top={int(top)}"
    )
    return _chamar_api("GET", f"/recorrencia/ranking?{params}")


@mcp.tool()
def get_tempo_real(unidade: str) -> str:
    """Dados em TEMPO REAL direto da API Proxxima (sem usar o banco). Use para
    panorama do dia, situação atual de uma unidade, ou quando precisar de dados
    frescos/atualizados. Retorna: abertas agora (total, por status e POR
    NATUREZA — ex.: quantas SEM ACESSO estão abertas neste momento), encerradas
    ontem, encerradas hoje (com quebra por natureza e produtiva/improdutiva),
    abertas hoje (por natureza), SLA vencido e sem técnico.

    Args:
        unidade: Unidade: CAMPINA GRANDE ou LAGOA SECA.
    """
    path = f"/diagnostico/tempo-real/{quote(unidade, safe='')}"
    return _chamar_api("GET", path)


@mcp.tool()
def get_atendimentos_agendados(
    unidade: str,
    data: Optional[str] = None,
) -> str:
    """Atendimentos AGENDADOS para uma data (hoje/amanhã/próximos) que já estão
    com equipe, por unidade e por natureza. Fonte: data_Hora_Agendamento_OS do
    Proxxima (coluna agendamento do banco). Use para perguntas do tipo 'quantos
    atendimentos temos agendado para amanhã em CG/LS' ou 'o que está agendado
    hoje por natureza'. Retorna total, com/sem equipe e a quebra por natureza.
    Não confundir com 'Aguardando Agendamento' (fila SEM data), que é a fila
    ainda não agendada.

    Args:
        unidade: Unidade: CAMPINA GRANDE ou LAGOA SECA.
        data: Data dos agendamentos (YYYY-MM-DD). Se omitido, usa AMANHÃ
            (dia seguinte ao atual).
    """
    amanha = datetime.now() + timedelta(days=1)
    dia = data or amanha.strftime("%Y-%m-%d")
    params = f"data={quote(dia, safe='')}"
    return _chamar_api("GET", f"/diagnostico/agendados/{quote(unidade, safe='')}?{params}")


@mcp.tool()
def get_planilha(aba: Optional[str] = None, limite: Optional[int] = None) -> str:
    """Lê dados da planilha Google Sheets. Primeiro chame sem aba para ver a
    lista de abas disponíveis. Depois chame com o nome da aba para ler os
    dados. Limite padrão: 200 linhas.

    Args:
        aba: Nome da aba da planilha. Se omitido, retorna a lista de abas.
        limite: Máximo de linhas retornadas (padrão: 200, máx: 2000).
    """
    if not aba:
        return _chamar_api("GET", "/planilha/abas")
    qs = f"?limite={int(limite)}" if limite is not None else ""
    return _chamar_api("GET", f"/planilha/{quote(aba, safe='')}{qs}")


@mcp.tool()
def get_relatorio_semanal(
    unidade: str,
    periodo_de: Optional[str] = None,
    periodo_ate: Optional[str] = None,
) -> str:
    """Gera um relatório semanal em .docx para uma unidade. Retorna o ID e a
    URL de download do relatório. Use quando o usuário pedir para gerar um
    relatório.

    Args:
        unidade: Unidade: CAMPINA GRANDE ou LAGOA SECA.
        periodo_de: Início do período (YYYY-MM-DD). Se omitido, usa a semana atual.
        periodo_ate: Fim do período (YYYY-MM-DD). Se omitido, usa a semana atual.
    """
    de, ate = _semana_atual()
    corpo = {
        "unidade": unidade,
        "periodo_de": periodo_de or de,
        "periodo_ate": periodo_ate or ate,
    }
    resultado = json.loads(_chamar_api("POST", "/relatorios", body=corpo))
    if isinstance(resultado, dict) and resultado.get("id"):
        resultado["download_url"] = f"{API_BASE}/relatorios/{resultado['id']}/download"
    return json.dumps(resultado, ensure_ascii=False, indent=2, default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()