"""Cliente do TOTVS Analytics (GoodData): KPIs, premiações e métricas.

Autenticação por dois cookies:
- ``GDCAuthSST``: session server token (validade ~7 dias, renovado manualmente).
- ``GDCAuthTT``: temporary token (obtido via ``GET /gdc/account/token``).

O cookie SST vem de ``settings.totvs_sst_cookie`` (variável de ambiente).
O cookie TT é obtido automaticamente pelo client a cada chamada de ``get_token()``.

Uso típico::

    from app.services.totvs_client import TotvsClient

    client = TotvsClient()
    try:
        kpi = client.execute_report(report_id="4890627", dashboard_id="124470")
    finally:
        client.close()
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://analytics.totvs.com.br"
WORKSPACE = "x1axmpyn93u81uio68w00y4arjxjgbq1"

# IDs dos reports conhecidos (extraídos do dashboard via DevTools)
REPORT_KPI_REPAROS = "4890627"
DASHBOARD_KPI = "124470"

REPORT_PREMIACAO_SUPERVISOR = "1464793"
DASHBOARD_PREMIACAO_SUPERVISOR = "2278082"

REPORT_PONTUACAO_DIA_TECNICO = "2837323"  # Pontuação por Dia x Técnico e Unidade

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class TotvsError(Exception):
    """Erro base do cliente TOTVS Analytics."""


class TotvsAuthError(TotvsError):
    """Cookie ausente, expirado ou sessão inválida."""


class TotvsRequestError(TotvsError):
    """Falha na comunicação com o TOTVS Analytics."""


class TotvsClient:
    """Cliente síncrono do TOTVS Analytics (GoodData), com renovação automática de token."""

    def __init__(self, sst_cookie: str | None = None) -> None:
        cookie = sst_cookie if sst_cookie is not None else settings.totvs_sst_cookie
        if not cookie:
            raise TotvsAuthError(
                "Cookie do TOTVS Analytics não configurado (TOTVS_SST_COOKIE ausente no .env)."
            )
        self.sst = cookie
        self.tt: str | None = None
        self.client = httpx.Client(timeout=30, follow_redirects=True)
        self._headers_base = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
            "x-gdc-accept": "application/json",
            "x-gdc-version": "3",
            "x-gdc-errorlevel": "15",
            "x-requested-with": "XMLHttpRequest",
        }

    def _cookies_dict(self) -> dict[str, str]:
        cookies = {"GDCAuthSST": self.sst, "locale": "en-US"}
        if self.tt:
            cookies["GDCAuthTT"] = self.tt
        return cookies

    def get_token(self) -> str:
        """Obtém ``GDCAuthTT`` via ``GET /gdc/account/token``.

        O token é cacheado na instância — só renova se ``self.tt`` for None.
        Retorna o valor do cookie TT (não é printado/logado).
        """
        if self.tt:
            return self.tt

        try:
            response = self.client.get(
                f"{BASE_URL}/gdc/account/token",
                headers=self._headers_base,
                cookies=self._cookies_dict(),
            )
        except httpx.HTTPError as exc:
            raise TotvsRequestError(f"Falha ao obter token TOTVS: {exc}") from exc

        if response.status_code in (401, 403):
            raise TotvsAuthError(
                f"Token TOTVS respondeu HTTP {response.status_code}: sessão inválida "
                "ou cookie GDCAuthSST expirado. Renove o cookie no navegador."
            )

        if response.status_code != 200:
            raise TotvsRequestError(f"Token TOTVS respondeu HTTP {response.status_code}.")

        # O token vem no header Set-Cookie: GDCAuthTT=...
        set_cookie = response.headers.get("set-cookie", "")
        if "GDCAuthTT=" in set_cookie:
            self.tt = set_cookie.split("GDCAuthTT=")[1].split(";")[0]
            logger.info("TOTVS token obtido com sucesso.")
            return self.tt

        raise TotvsAuthError("Resposta do token TOTVS não contém GDCAuthTT.")

    def execute_report(
        self,
        report_id: str,
        dashboard_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Executa um report/visualização e retorna o ``execResult`` completo.

        Args:
            report_id: ID numérico do report (obj ID no GoodData).
            dashboard_id: ID numérico do dashboard (opcional, usado como contexto).
            filters: Filtros extras no formato GoodData (expression + tree).

        Returns:
            Dict com ``dataResult`` (URL para buscar os dados) e ``reportView``.
        """
        self.get_token()  # garante que temos TT

        report_uri = f"/gdc/md/{WORKSPACE}/obj/{report_id}"
        context: dict[str, Any] = {"report": report_uri}
        if dashboard_id:
            context["context"] = {"dashboard": f"/gdc/md/{WORKSPACE}/obj/{dashboard_id}"}
        if filters:
            if "context" not in context:
                context["context"] = {}
            context["context"]["filters"] = filters

        body = {"report_req": context}

        try:
            response = self.client.post(
                f"{BASE_URL}/gdc/app/projects/{WORKSPACE}/execute",
                headers=self._headers_base,
                cookies=self._cookies_dict(),
                json=body,
            )
        except httpx.HTTPError as exc:
            raise TotvsRequestError(f"Falha ao executar report {report_id}: {exc}") from exc

        if response.status_code in (401, 403):
            # Token pode ter expirado — limpa e tenta uma vez
            self.tt = None
            self.get_token()
            try:
                response = self.client.post(
                    f"{BASE_URL}/gdc/app/projects/{WORKSPACE}/execute",
                    headers=self._headers_base,
                    cookies=self._cookies_dict(),
                    json=body,
                )
            except httpx.HTTPError as exc:
                raise TotvsRequestError(f"Falha ao executar report {report_id} (retry): {exc}") from exc

        if response.status_code not in (200, 201):
            raise TotvsRequestError(
                f"Report {report_id} respondeu HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise TotvsRequestError(f"Resposta do report {report_id} não é JSON válido.") from exc

    def get_data_result(self, data_result_path: str) -> dict[str, Any]:
        """Busca os dados brutos de um ``dataResult``.

        Args:
            data_result_path: Caminho relativo (ex: ``/gdc/md/.../dataResult/123``).

        Returns:
            Dict com ``xtab_data`` (dados em formato cross-tab).
        """
        self.get_token()

        url = f"{BASE_URL}{data_result_path}" if data_result_path.startswith("/") else data_result_path

        try:
            response = self.client.get(
                url,
                headers=self._headers_base,
                cookies=self._cookies_dict(),
            )
        except httpx.HTTPError as exc:
            raise TotvsRequestError(f"Falha ao buscar dataResult: {exc}") from exc

        if response.status_code in (401, 403):
            raise TotvsAuthError(
                f"dataResult respondeu HTTP {response.status_code}: sessão inválida."
            )

        if response.status_code != 200:
            raise TotvsRequestError(f"dataResult respondeu HTTP {response.status_code}.")

        try:
            return response.json()
        except ValueError as exc:
            raise TotvsRequestError("Resposta do dataResult não é JSON válido.") from exc

    def execute_and_get_data(
        self,
        report_id: str,
        dashboard_id: str | None = None,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Executa um report e retorna os dados brutos (dataResult parseado).

        Combina ``execute_report`` + ``get_data_result`` em uma chamada.
        Retorna o ``xtab_data`` completo.
        """
        exec_result = self.execute_report(report_id, dashboard_id, filters)
        data_path = exec_result.get("execResult", {}).get("dataResult")
        if not data_path:
            raise TotvsRequestError(f"Report {report_id} não retornou dataResult.")
        return self.get_data_result(data_path)

    @staticmethod
    def parse_xtab_data(xtab: dict) -> list[dict[str, str]]:
        """Converte ``xtab_data`` em lista de dicts legíveis.

        O formato cross-tab do GoodData tem:
        - ``columns.lookups``: mapa de índice → nome da coluna
        - ``rows.lookups``: mapa de índice → nome da linha
        - ``data``: matriz de valores

        Retorna lista de dicts onde cada chave é o nome da coluna.
        """
        col_lookups = xtab.get("columns", {}).get("lookups", [{}])
        row_lookups = xtab.get("rows", {}).get("lookups", [{}])
        data = xtab.get("data", [])

        # Mapeia índice → nome da coluna
        col_names: dict[int, str] = {}
        for lookup in col_lookups:
            for idx_str, nome in lookup.items():
                col_names[int(idx_str)] = nome

        # Mapeia índice → nome da linha
        row_names: dict[int, str] = {}
        for lookup in row_lookups:
            for idx_str, nome in lookup.items():
                row_names[int(idx_str)] = nome

        resultados = []
        for row_idx, row_data in enumerate(data):
            row_dict: dict[str, str] = {}
            # Adiciona o nome da linha se houver
            if row_idx in row_names:
                row_dict["linha"] = row_names[row_idx]
            for col_idx, valor in enumerate(row_data):
                col_name = col_names.get(col_idx, f"col_{col_idx}")
                row_dict[col_name] = valor
            resultados.append(row_dict)

        return resultados

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> TotvsClient:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
