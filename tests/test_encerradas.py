"""Testes das encerradas por período (GET /diagnostico/encerradas/{unidade}).

Cobre: tipo (prod/improd/cancelada), quebra por natureza e por dia, a data de
referência (fechamento; fallback abertura), taxa de produtividade e a ordem.
Sem banco (fake DB no padrão do projeto).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.routers.diagnostico import _encerradas_por_periodo
from app.schemas.diagnostico import EncerradasResumo

BR = ZoneInfo("America/Sao_Paulo")
SEG = date(2026, 8, 24)
SAB = date(2026, 8, 29)
DOM = date(2026, 8, 30)


def _dt(d: date, hora: str) -> datetime:
    return datetime.strptime(f"{d:%d/%m/%Y} {hora}", "%d/%m/%Y %H:%M").replace(tzinfo=BR)


SEG_HM = _dt(SEG, "10:00")
SAB_17 = _dt(SAB, "17:00")


class Row:
    def __init__(self, natureza, status, fechamento=None, abertura=None):
        self.natureza = natureza
        self.status = status
        self.fechamento = fechamento
        self.abertura = abertura


class FakeResult:
    def __init__(self, linhas):
        self._linhas = linhas

    def all(self):
        return self._linhas


class FakeDB:
    def __init__(self, linhas):
        self.linhas = linhas

    def execute(self, stmt):
        return FakeResult(self.linhas)


class TestEncerradasPorPeriodo:
    def test_quebra_por_natureza_e_dia_com_taxa(self):
        db = FakeDB(
            [
                Row("INSTALAÇÃO", "Fechada Produtiva", SEG_HM, SEG_HM),
                Row("INSTALAÇÃO", "Fechada Produtiva", SEG_HM, SEG_HM),
                Row("SEM ACESSO", "Fechada Improdutiva", SAB_17, SAB_17),
                Row("SEM ACESSO", "Cancelado", None, SEG_HM),
                Row("DEFEITO INTERNO", "Fechada Produtiva", None, SEG_HM),  # fallback abertura
            ]
        )
        res = _encerradas_por_periodo(db, "CAMPINA GRANDE", SEG, DOM)

        assert isinstance(res, EncerradasResumo)
        assert res.unidade == "CAMPINA GRANDE"
        assert res.produtivas == 3
        assert res.improdutivas == 1
        assert res.canceladas == 1
        assert res.total_encerradas == 4
        assert res.taxa_produtiva == round(3 / 4, 4)

        por_nat = {n.natureza: n for n in res.por_natureza}
        assert por_nat["INSTALAÇÃO"].total == 2
        assert por_nat["INSTALAÇÃO"].produtivas == 2
        assert por_nat["SEM ACESSO"].total == 2
        assert por_nat["SEM ACESSO"].improdutivas == 1
        assert por_nat["SEM ACESSO"].canceladas == 1
        assert por_nat["DEFEITO INTERNO"].produtivas == 1

        por_dia = {d.data: d for d in res.por_dia}
        assert por_dia[SEG].total == 4  # 2+1 inst + 1 cancelado + 1 defeito (fallback)
        assert por_dia[SAB].total == 1

    def test_cancelado_fora_do_total_encerradas(self):
        db = FakeDB([Row("X", "Cancelado", SEG_HM, SEG_HM)])
        res = _encerradas_por_periodo(db, "LAGOA SECA", SEG, DOM)
        assert res.total_encerradas == 0
        assert res.canceladas == 1
        assert res.taxa_produtiva is None

    def test_sem_registros(self):
        res = _encerradas_por_periodo(FakeDB([]), "CAMPINA GRANDE", SEG, DOM)
        assert res.total_encerradas == 0
        assert res.por_natureza == []
        assert res.por_dia == []
        assert res.taxa_produtiva is None

    def test_ordena_natureza_por_total_desc(self):
        db = FakeDB(
            [
                Row("A", "Fechada Produtiva", SEG_HM, SEG_HM),
                Row("B", "Fechada Produtiva", SEG_HM, SEG_HM),
                Row("A", "Fechada Produtiva", SEG_HM, SEG_HM),
            ]
        )
        res = _encerradas_por_periodo(db, "CAMPINA GRANDE", SEG, DOM)
        assert [n.natureza for n in res.por_natureza] == ["A", "B"]

    def test_natureza_vazia_vira_rotulo(self):
        db = FakeDB([Row(None, "Fechada Produtiva", SEG_HM, SEG_HM)])
        res = _encerradas_por_periodo(db, "CAMPINA GRANDE", SEG, DOM)
        assert res.por_natureza[0].natureza == "SEM NATUREZA"