"""Testes do job de sync do painel-ope: parsers de payload externo.

Cobre _parse_data_key (dataKey YYYYMMDD) e _semana_atual. O bug de
`date.strptime` foi real em produção (AttributeError) — o parser é ponto
frágil (formato do painel pode mudar).
"""

from datetime import date

from app.jobs.sync_painel_ope import _parse_data_key, _semana_atual


class TestParseDataKey:
    def test_formato_yyyymmdd(self):
        assert _parse_data_key("20260828") == date(2026, 8, 28)

    def test_valor_inteiro(self):
        assert _parse_data_key(20260828) == date(2026, 8, 28)

    def test_vazio_retorna_none(self):
        assert _parse_data_key("") is None
        assert _parse_data_key(None) is None

    def test_formato_invalido_retorna_none(self):
        assert _parse_data_key("28/08/2026") is None
        assert _parse_data_key("abc") is None


class TestSemanaAtual:
    def test_segunda_a_domingo(self):
        segunda, domingo = _semana_atual(date(2026, 8, 30))  # domingo
        assert segunda == date(2026, 8, 24)
        assert domingo == date(2026, 8, 30)

    def test_quarta(self):
        segunda, domingo = _semana_atual(date(2026, 8, 26))  # quarta
        assert segunda == date(2026, 8, 24)
        assert domingo == date(2026, 8, 30)