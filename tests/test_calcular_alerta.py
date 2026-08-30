"""Testes da lógica de alerta do cruzamento (Sprint 4).

Limites calibrados com o usuário em 2026-08-15:
- LIMITE_REABERTURA = 1: qualquer reabertura (>=1) em menos de 30 dias para o
  mesmo cliente já é crítico — definição de negócio, não limiar estatístico.
  Por isso a comparação é >= (1 reabertura já dispara).
- LIMITE_BANCO_HORAS = 8.0 e META_INSPECAO = 7.0 mantidos. Desde 2026-08-30 o
  limite vale para o SALDO do banco de horas (planilha pública), que substitui
  o HE do painel-ope.
"""

from app.services.cruzamento import (
    LIMITE_BANCO_HORAS,
    LIMITE_REABERTURA,
    META_INSPECAO,
    _calcular_alerta,
)


class TestCalcularAlerta:
    def test_sem_alerta(self):
        rec = {"reabriu_total": 0}
        bh = {"saldo": LIMITE_BANCO_HORAS}
        insp = {"pontuacao": META_INSPECAO}
        assert _calcular_alerta(rec, bh, insp) == []

    def test_uma_reabertura_ja_alerta(self):
        # Nova regra de negócio: qualquer reabertura é crítica.
        rec = {"reabriu_total": 1}
        assert _calcular_alerta(rec, {"saldo": 0}, None) == ["recorrência de reabertura acima do limite"]

    def test_duas_reaberturas_alerta(self):
        rec = {"reabriu_total": 2}
        assert _calcular_alerta(rec, {"saldo": 0}, None) == ["recorrência de reabertura acima do limite"]

    def test_limite_exato_dispara(self):
        # Com LIMITE_REABERTURA=1 e comparação >=, o limite exato dispara.
        assert _calcular_alerta({"reabriu_total": LIMITE_REABERTURA}, {"saldo": 0}, None) == [
            "recorrência de reabertura acima do limite"
        ]

    def test_zero_reaberturas_nao_alerta(self):
        assert _calcular_alerta({"reabriu_total": 0}, {"saldo": 0}, None) == []

    def test_saldo_acima_do_limite(self):
        assert _calcular_alerta({"reabriu_total": 0}, {"saldo": LIMITE_BANCO_HORAS + 0.1}, None) == [
            "saldo de banco de horas acima do limite semanal"
        ]

    def test_saldo_negativo_nao_alerta(self):
        # Saldo negativo (banco a dever horas) não dispara alerta.
        assert _calcular_alerta({"reabriu_total": 0}, {"saldo": -3.5}, None) == []

    def test_inspecao_abaixo_da_meta(self):
        insp = {"pontuacao": META_INSPECAO - 0.5}
        assert _calcular_alerta({"reabriu_total": 0}, {"saldo": 0}, insp) == [
            "pontuação de inspeção abaixo da meta"
        ]

    def test_inspecao_inexistente_nao_alerta(self):
        assert _calcular_alerta({"reabriu_total": 0}, {"saldo": 0}, None) == []

    def test_multiplos_alertas(self):
        rec = {"reabriu_total": LIMITE_REABERTURA}
        bh = {"saldo": LIMITE_BANCO_HORAS + 2}
        insp = {"pontuacao": META_INSPECAO - 1}
        alertas = _calcular_alerta(rec, bh, insp)
        assert len(alertas) == 3

    def test_saldo_ausente_nao_alerta(self):
        assert _calcular_alerta({"reabriu_total": 0}, {}, None) == []