"""Cliente genérico do Google Sheets.

Usa service account via ``gspread``. As credenciais vêm de variável de ambiente
(arquivo JSON da service account ou string JSON). Sem credenciais, apenas loga
warning e retorna listas vazias — o sistema não falha por falta dessa fonte.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class SheetsClient:
    """Leitura genérica de qualquer aba da planilha."""

    def __init__(self) -> None:
        self._gc = None
        self._spreadsheet = None
        creds = self._load_creds()
        url = settings.sheets_spreadsheet_url
        if not creds or not url:
            logger.warning("[sheets] sem credenciais ou URL configurados — planilha indisponível.")
            return
        try:
            import gspread

            self._gc = gspread.service_account_from_dict(creds)
            self._spreadsheet = self._gc.open_by_url(url)
        except Exception as exc:
            logger.error("[sheets] falha ao inicializar client: %s", exc)
            self._gc = None
            self._spreadsheet = None

    @staticmethod
    def _load_creds() -> dict | None:
        """Carrega credenciais de arquivo ou de string JSON."""
        if settings.sheets_service_account_file:
            path = Path(settings.sheets_service_account_file)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent.parent / path
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.error("[sheets] falha ao ler arquivo %s: %s", path, exc)
                    return None
            logger.warning("[sheets] arquivo de credenciais não encontrado: %s", path)
        if settings.sheets_service_account_json:
            try:
                return json.loads(settings.sheets_service_account_json)
            except Exception as exc:
                logger.error("[sheets] falha ao parsear JSON de credenciais: %s", exc)
                return None
        return None

    @property
    def disponivel(self) -> bool:
        return self._spreadsheet is not None

    def listar_abas(self) -> list[str]:
        """Retorna nomes de todas as abas da planilha."""
        if not self._spreadsheet:
            return []
        try:
            return [ws.title for ws in self._spreadsheet.worksheets()]
        except Exception as exc:
            logger.error("[sheets] falha ao listar abas: %s", exc)
            return []

    def ler_aba(self, nome_aba: str) -> list[dict]:
        """Lê todas as linhas de uma aba como lista de dicts (header → valor).

        Pula linhas totalmente vazias. Usa a primeira linha como header.
        """
        if not self._spreadsheet:
            return []
        try:
            ws = self._spreadsheet.worksheet(nome_aba)
        except Exception:
            logger.warning("[sheets] aba '%s' não encontrada", nome_aba)
            return []
        try:
            valores = ws.get_all_values()
        except Exception as exc:
            logger.error("[sheets] falha ao ler aba '%s': %s", nome_aba, exc)
            return []
        if not valores:
            return []
        headers = [str(c).strip() for c in valores[0]]
        registros = []
        for i, linha in enumerate(valores[1:], start=2):
            if not any(str(v).strip() for v in linha):
                continue
            linha_dict = {
                "__linha": i,
                **{h: (str(v).strip() if v is not None else "") for h, v in zip(headers, linha)},
            }
            registros.append(linha_dict)
        logger.info("[sheets] aba '%s': %d registros lidos", nome_aba, len(registros))
        return registros

    def ler_todas(self) -> dict[str, list[dict]]:
        """Lê todas as abas. Retorna {nome_aba: [registros]}."""
        if not self._spreadsheet:
            return {}
        resultado = {}
        for nome in self.listar_abas():
            dados = self.ler_aba(nome)
            if dados:
                resultado[nome] = dados
        return resultado

    def aba_inspecao(self) -> list[dict]:
        """Legacy: lê a aba de inspeção (mantido para compatibilidade)."""
        return self.ler_aba(settings.sheets_aba_inspecao)
