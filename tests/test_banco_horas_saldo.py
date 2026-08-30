"""Testes da nova fonte de banco de horas (planilha pública) — Sprint 8.

Cobre: parsing do CSV público (client), montagem de registros (job) e os
helpers de saldo do cruzamento (com sqlite em memória).
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.jobs.sync_banco_horas_saldo import _montar_registros
from app.models.banco_horas_saldo import BancoHorasSaldo
from app.services import banco_horas_sheets_client as sheets
from app.services.banco_horas_sheets_client import (
    BancoHorasSheetsClient,
    BancoHorasSheetsError,
    _decodificar,
    parse_data_br,
    parse_saldo_br,
    parse_saldo_csv,
)
from app.services.cruzamento import (
    buscar_banco_horas_tecnico,
    buscar_saldo_banco_unidade,
    buscar_ultimos_saldos,
)


CSV_BOM_COM_MILHAR = (
    "DATA,NOME,UNIDADE,COORDENADOR,SUPERVISOR,CARGO,TIPO,SALDO,VARIACAO,STATUS\r\n"
    '18/05/2026,TEC A,CAMPINA GRANDE,LUIZ FELIPE,DOUGLAS CARDOSO,Técnico,TECNICO,"7,55"\n'
)


class TestDecodificar:
    def test_utf8_sig(self):
        conteudo = "Tipo\r\nTécnico\r\n".encode("utf-8-sig")
        assert _decodificar(conteudo) == "Tipo\r\nTécnico\r\n"

    def test_cp1252(self):
        conteudo = b"Tipo\r\nT\xe9cnico\r\n"
        assert _decodificar(conteudo) == "Tipo\r\nTécnico\r\n"


class TestParseDataSaldo:
    def test_data_dd_mm_aaaa(self):
        assert parse_data_br("18/05/2026") == date(2026, 5, 18)

    def test_data_vazia(self):
        assert parse_data_br("") is None
        assert parse_data_br(None) is None

    def test_data_invalida(self):
        assert parse_data_br("32/13/2026") is None

    def test_saldo_virgula(self):
        assert parse_saldo_br("7,55") == 7.55

    def test_saldo_inteiro(self):
        assert parse_saldo_br("0") == 0.0

    def test_saldo_com_milhar(self):
        assert parse_saldo_br("1.234,56") == 1234.56

    def test_saldo_vazio(self):
        assert parse_saldo_br("") is None
        assert parse_saldo_br(None) is None

    def test_saldo_ilegivel(self):
        assert parse_saldo_br("abc") is None


class TestParseSaldoCsv:
    def test_csv_real(self):
        linhas = parse_saldo_csv(CSV_BOM_COM_MILHAR)
        assert len(linhas) == 1
        assert linhas[0]["NOME"] == "TEC A"
        assert linhas[0]["SALDO"] == "7,55"
        assert linhas[0]["CARGO"] == "Técnico"

    def test_sem_coluna_obrigatoria_levanta(self):
        with pytest.raises(BancoHorasSheetsError):
            parse_saldo_csv("DATA,NOME,UNIDADE\r\nx,y,z\r\n")

    def test_bom_removido_das_colunas(self):
        linhas = parse_saldo_csv("\ufeffDATA,NOME,UNIDADE,SALDO\n01/01/2026,A,CG,0\n")
        assert "DATA" in linhas[0]

    def test_respeita_ordem_e_casos(self):
        linhas = parse_saldo_csv("data,nome,unidade,saldo\n01/01/2026,A,CG,1\n")
        assert linhas[0]["DATA"] == "01/01/2026"


class TestMontarRegistros:
    def _linha(self, **kwargs):
        base = {
            "DATA": "18/05/2026",
            "NOME": "TEC A",
            "UNIDADE": "CAMPINA GRANDE",
            "COORDENADOR": "COORD",
            "SUPERVISOR": "SUP",
            "CARGO": "TECNICO",
            "TIPO": "TECNICO",
            "SALDO": "7,55",
            "VARIACAO": "",
            "STATUS": "POSITIVO",
        }
        base.update(kwargs)
        return base

    def test_filtra_somente_unidades_alvo(self):
        linhas = [
            self._linha(NOME="TEC A"),
            self._linha(NOME="TEC B", UNIDADE="LAGOA SECA"),
            self._linha(NOME="TEC C", UNIDADE="FILADELFIA"),
        ]
        regs, stats = _montar_registros(linhas)
        assert [r["tecnico"] for r in regs] == ["TEC A", "TEC B"]
        assert stats["ignoradas_outra_unidade"] == 1
        assert stats["por_unidade"] == {"CAMPINA GRANDE": 1, "LAGOA SECA": 1}

    def test_saldo_convertido(self):
        regs, _ = _montar_registros([self._linha(SALDO="1.234,56")])
        assert regs[0]["saldo"] == 1234.56

    def test_data_vira_madrugada(self):
        regs, _ = _montar_registros([self._linha(DATA="18/05/2026")])
        assert regs[0]["data"] == datetime(2026, 5, 18, 0, 0)

    def test_ignora_sem_data_e_sem_saldo(self):
        regs, stats = _montar_registros(
            [self._linha(DATA=""), self._linha(SALDO="")]
        )
        assert regs == []
        assert stats["ignoradas_sem_data"] == 1
        assert stats["ignoradas_sem_saldo"] == 1


@pytest.fixture()
def session_bh():
    engine = create_engine("sqlite://")
    BancoHorasSaldo.__table__.create(engine)
    s = Session(engine)
    linhas = [
        ("TEC A", "CAMPINA GRANDE", datetime(2026, 5, 18), 7.55),
        ("TEC A", "CAMPINA GRANDE", datetime(2026, 5, 19), 9.10),
        ("TEC B", "CAMPINA GRANDE", datetime(2026, 5, 18), 3.00),
        ("TEC C", "LAGOA SECA", datetime(2026, 5, 18), 12.00),
    ]
    for i, (tec, uni, data, saldo) in enumerate(linhas, start=1):
        s.add(BancoHorasSaldo(id=i, tecnico=tec, unidade=uni, data=data, saldo=saldo))
    s.commit()
    yield s
    s.close()


DE = date(2026, 5, 1)
ATE = date(2026, 5, 31)


class TestCruzamentoSaldo:
    def test_ultimos_saldos_filtra_unidade(self, session_bh):
        regs = buscar_ultimos_saldos(session_bh, DE, ATE, unidade="CAMPINA GRANDE")
        saldos = {(r.tecnico, r.data): float(r.saldo) for r in regs}
        assert set(r.tecnico for r in regs) == {"TEC A", "TEC B"}
        assert saldos[("TEC A", datetime(2026, 5, 19, 0, 0))] == 9.10

    def test_ultimos_saldos_sem_unidade(self, session_bh):
        regs = buscar_ultimos_saldos(session_bh, DE, ATE)
        assert {r.tecnico for r in regs} == {"TEC A", "TEC B", "TEC C"}

    def test_saldo_banco_unidade_total(self, session_bh):
        resumo = buscar_saldo_banco_unidade(session_bh, "CAMPINA GRANDE", DE, ATE)
        assert resumo["total_saldo"] == 12.10  # 9.10 (TEC A) + 3.00 (TEC B)
        assert len(resumo["tecnicos"]) == 2

    def test_banco_horas_tecnico_sem_infracoes(self, session_bh, monkeypatch):
        monkeypatch.setattr("app.services.cruzamento._snapshots_no_periodo", lambda *a, **k: [])
        res = buscar_banco_horas_tecnico(session_bh, "TEC A", DE, ATE)
        assert res["saldo"] == 9.10
        assert res["dias_com_saldo"] == 2
        assert res["infracoes"] == 0

    def test_banco_horas_tecnico_sem_registro(self, session_bh, monkeypatch):
        monkeypatch.setattr("app.services.cruzamento._snapshots_no_periodo", lambda *a, **k: [])
        res = buscar_banco_horas_tecnico(session_bh, "SEM REGISTRO", DE, ATE)
        assert res["saldo"] is None
        assert res["dias_com_saldo"] == 0


class TestClientUrl:
    class _FakeResp:
        def __init__(self, conteudo: bytes, status: int = 200):
            self.content = conteudo
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                import httpx

                raise httpx.HTTPStatusError(
                    "erro", request=None, response=None
                )

    class _FakeHttpxClient:
        def __init__(self, resp):
            self._resp = resp
            self._url = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            self._url = url
            return self._resp

    def test_fetch_saldo_parseia_e_usa_a_url(self, monkeypatch):
        resp = self._FakeResp(CSV_BOM_COM_MILHAR.encode("utf-8-sig"))
        fake = self._FakeHttpxClient(resp)
        monkeypatch.setattr(sheets.httpx, "Client", lambda *a, **k: fake)
        linhas = BancoHorasSheetsClient().fetch_saldo(url="https://exemplo.com/csv")
        assert fake._url == "https://exemplo.com/csv"
        assert linhas[0]["NOME"] == "TEC A"
        assert linhas[0]["SALDO"] == "7,55"

    def test_http_error_repassa(self, monkeypatch):
        resp = self._FakeResp(b"", status=404)
        fake = self._FakeHttpxClient(resp)
        monkeypatch.setattr(sheets.httpx, "Client", lambda *a, **k: fake)
        import httpx

        with pytest.raises(httpx.HTTPStatusError):
            BancoHorasSheetsClient().fetch_saldo(url="https://exemplo.com/csv")