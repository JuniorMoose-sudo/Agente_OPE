"""Testes do job de sync da pontuação (n8n aniel-aovivo → pontuacao_tecnico_dia).

Cobre: filtro da semana, flag nao_pontua, soma por dia e o UPSERT por
(tecnico, unidade, data) — regressão do padrão do sync de recorrência.
"""

import pytest

from app.jobs.sync_pontuacao import (
    _dias_da_semana,
    _montar_linhas,
    _nao_pontua_set,
    _semana_atual_dk,
    _sync_para_db,
)

DATAS_SEMANA = _dias_da_semana("2026-08-24", "2026-08-30")
PAYLOAD = {
    "fechSemana": [
        {"os": "1/1", "tecnico": "TEC A", "uni": "CAMPINA GRANDE", "encDK": "20260824", "pontos": 3.5},
        {"os": "2/1", "tecnico": "TEC A", "uni": "CAMPINA GRANDE", "encDK": "20260824", "pontos": 1.5},
        {"os": "3/1", "tecnico": "TEC A", "uni": "CAMPINA GRANDE", "encDK": "20260829", "pontos": 2},
        {"os": "4/1", "tecnico": "TEC B", "uni": "LAGOA SECA", "encDK": "20260825", "pontos": 8},
        {"os": "5/1", "tecnico": "TEC C", "uni": "LAGOA SECA", "encDK": "20260731", "pontos": 9},
    ],
    "naoPontua": ["tec a"],
}


class FakeDB:
    def __init__(self):
        self.executados = []
        self.chamou_commit = False

    def execute(self, stmt):
        self.executados.append(stmt)
        return None

    def commit(self):
        self.chamou_commit = True


class TestNaoPontuaSet:
    def test_upper_e_strip(self):
        assert _nao_pontua_set({"naoPontua": ["tec a", "  alguem  ", "", 42]}) == {
            "TEC A",
            "ALGUEM",
            "42",
        }


class TestDiasDaSemana:
    def test_inclusive_seg_a_dom(self):
        assert _dias_da_semana("2026-08-24", "2026-08-30") == DATAS_SEMANA
        assert len(DATAS_SEMANA) == 7

    def test_semana_atual_seg_a_dom(self):
        # sem monkeypatch: _semana_atual_dk aceita data de referência explícita
        assert _semana_atual_dk(__import__("datetime").date(2026, 8, 28)) == (
            "2026-08-24",
            "2026-08-30",
        )


class TestMontarLinhas:
    def test_soma_redonda_e_flag_nao_pontua(self):
        linhas = _montar_linhas(PAYLOAD, DATAS_SEMANA)
        por_dia = {f'{l["tecnico"]}|{l["data"]:%Y-%m-%d}': l for l in linhas}
        assert "TEC A|2026-08-24" in por_dia
        assert "TEC A|2026-08-29" in por_dia
        assert por_dia["TEC A|2026-08-24"]["pontos"] == 5.0  # 3.5 + 1.5 na SEG
        assert por_dia["TEC A|2026-08-29"]["pontos"] == 2.0  # sábado
        assert por_dia["TEC A|2026-08-24"]["nao_pontua"] is True
        assert por_dia["TEC A|2026-08-24"]["unidade"] == "CAMPINA GRANDE"
        assert por_dia["TEC B|2026-08-25"]["pontos"] == 8.0
        assert por_dia["TEC B|2026-08-25"]["nao_pontua"] is False
        assert "TEC C" not in " ".join(l["tecnico"] for l in linhas)  # dia fora da semana

    def test_sem_payload_gera_lista_vazia(self):
        assert _montar_linhas({"fechSemana": [], "naoPontua": []}, DATAS_SEMANA) == []

    def test_dia_fora_da_semana_ignorado(self):
        linhas = _montar_linhas(PAYLOAD, _dias_da_semana("2026-07-27", "2026-08-02"))
        por_tecnico = {l["tecnico"] for l in linhas}
        assert por_tecnico == {"TEC C"}


class TestSyncParaDb:
    def test_grava_com_upsert_e_commit(self):
        db = FakeDB()
        gravados, fora = _sync_para_db(db, PAYLOAD, DATAS_SEMANA)
        assert gravados == 3  # TEC A (SEG+SAB) e TEC B (TER)
        assert fora == 1  # 20260731 fora da semana
        stmt = db.executados[0]
        insert_sql = str(stmt)
        assert "INSERT INTO pontuacao_tecnico_dia" in insert_sql
        assert "ON CONFLICT (tecnico, unidade, data) DO UPDATE" in insert_sql
        assert db.chamou_commit is True

    def test_sem_linhas_nao_executa_insert(self):
        db = FakeDB()
        gravados, fora = _sync_para_db(db, {"fechSemana": [], "naoPontua": []}, DATAS_SEMANA)
        assert gravados == 0
        assert fora == 0
        assert db.executados == []