"""Testes do job de sincronização da recorrência pelo painel Operações."""

import os

import pytest

import app.jobs.sync_recorrencia_painel as job_mod
from app.jobs.sync_recorrencia_painel import sync_recorrencia_painel as sync_recorrencia

XLSX_BYTES = b"PK\x03\x04conteudo-fake"
MES = "2026-08"

CHAMADAS = []


class _FakeClient:
    def __init__(self, fallho=False):
        self._falhou = fallho
        self.baixados = []

    def fetch_analitico(self, unidade, mes):
        self.baixados.append((unidade, mes))
        if self._falhou:
            from app.services.operacoes_client import OperacoesAuthError

            raise OperacoesAuthError("sessão expirada")
        return XLSX_BYTES

    def close(self):
        pass


class _FakeDB:
    def close(self):
        pass


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    CHAMADAS.clear()
    monkeypatch.setattr(
        job_mod,
        "OperacoesClient",
        lambda *a, **k: _FakeClient(fallho=k.pop("falhou", False)),
    )
    monkeypatch.setattr(
        job_mod,
        "importar_recorrencia",
        lambda caminho, db: {"importadas": 1, "sem_tecnico": 0, "com_recorrencia": 1},
    )
    monkeypatch.setattr(job_mod, "SessionLocal", lambda: _FakeDB())
    CHAMADAS.append("ok")


def test_successo_importa_duas_unidades(monkeypatch):
    importados = []

    def _imp(caminho, db):
        importados.append((os.path.basename(caminho), db))
        return {"importadas": 10, "sem_tecnico": 1, "com_recorrencia": 2}

    monkeypatch.setattr(job_mod, "importar_recorrencia", _imp)

    resultado = sync_recorrencia(mes=MES)

    assert set(resultado) == {"UNIDADE CAMPINA GRANDE", "UNIDADE LAGOA SECA"}
    assert resultado["UNIDADE CAMPINA GRANDE"]["importadas"] == 10
    # arquivos temporários copiados e removidos
    assert all(p.startswith("recorrencia_painel_") and p.endswith(".xlsx") for p, _ in importados)
    assert all(not os.path.exists(p) for p, _ in importados)


def test_mes_atual_mantem_formato():
    mes = job_mod._mes_atual()
    assert len(mes) == 7 and mes[4] == "-" and int(mes[:4]) > 2000


def test_auth_error_dispara_alerta_telegram_e_relanca(monkeypatch):
    alertas = []
    monkeypatch.setattr(job_mod, "avisar_telegram", lambda msg: alertas.append(msg))
    monkeypatch.setattr(job_mod, "OperacoesClient", lambda *a, **k: _FakeClient(fallho=True))

    from app.services.operacoes_client import OperacoesAuthError

    with pytest.raises(OperacoesAuthError):
        sync_recorrencia(mes=MES)

    assert len(alertas) == 1
    assert "cookie do painel Operações" in alertas[0].lower() or "OPERACOES_SESSION_COOKIE" in alertas[0]