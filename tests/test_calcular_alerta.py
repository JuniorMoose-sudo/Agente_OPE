"""Testes da lógica de alerta do cruzamento (Sprint 4).

Limites calibrados com o usuário em 2026-08-15:
- LIMITE_REABERTURA = 1: qualquer reabertura (>=1) em menos de 30 dias para o
  mesmo cliente já é crítico — definição de negócio, não limiar estatístico.
  Por isso a comparação é >= (1 reabertura já dispara).
- LIMITE_HE_SEMANAL = 8.0 e META_INSPECAO = 7.0 mantidos.
"""

from app.services.cruzamento import (
    LIMITE_HE_SEMANAL,
    LIMITE_REABERTURA,
    META_INSPECAO,
    _calcular_alerta,
)


class TestCalcularAlerta:
    def test_sem_alerta(self):
        rec = {"reabriu_total": 0}
        bh = {"he_horas": LIMITE_HE_SEMANAL}
        insp = {"pontuacao": META_INSPECAO}
        assert _calcular_alerta(rec, bh, insp) == []

    def test_uma_reabertura_ja_alerta(self):
        # Nova regra de negócio: qualquer reabertura é crítica.
        rec = {"reabriu_total": 1}
        assert _calcular_alerta(rec, {"he_horas": 0}, None) == ["recorrência de reabertura acima do limite"]

    def test_duas_reaberturas_alerta(self):
        rec = {"reabriu_total": 2}
        assert _calcular_alerta(rec, {"he_horas": 0}, None) == ["recorrência de reabertura acima do limite"]

    def test_limite_exato_dispara(self):
        # Com LIMITE_REABERTURA=1 e comparação >=, o limite exato dispara.
        assert _calcular_alerta({"reabriu_total": LIMITE_REABERTURA}, {"he_horas": 0}, None) == [
            "recorrência de reabertura acima do limite"
        ]

    def test_zero_reaberturas_nao_alerta(self):
        assert _calcular_alerta({"reabriu_total": 0}, {"he_horas": 0}, None) == []

    def test_he_acima_do_limite(self):
        assert _calcular_alerta({"reabriu_total": 0}, {"he_horas": LIMITE_HE_SEMANAL + 0.1}, None) == [
            "HE acima do limite semanal"
        ]

    def test_inspecao_abaixo_da_meta(self):
        insp = {"pontuacao": META_INSPECAO - 0.5}
        assert _calcular_alerta({"reabriu_total": 0}, {"he_horas": 0}, insp) == [
            "pontuação de inspeção abaixo da meta"
        ]

    def test_inspecao_inexistente_nao_alerta(self):
        assert _calcular_alerta({"reabriu_total": 0}, {"he_horas": 0}, None) == []

    def test_multiplos_alertas(self):
        rec = {"reabriu_total": LIMITE_REABERTURA}
        bh = {"he_horas": LIMITE_HE_SEMANAL + 2}
        insp = {"pontuacao": META_INSPECAO - 1}
        alertas = _calcular_alerta(rec, bh, insp)
        assert len(alertas) == 3

    def test_he_ausente_nao_alerta(self):
        assert _calcular_alerta({"reabriu_total": 0}, {}, None) == []
