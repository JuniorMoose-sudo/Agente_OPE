"""Testes da checagem diária de cookie do painel-ope.

Cobre os 4 caminhos: ausente, inválido (parse/exp), sessão invalidada no
servidor (401 na sonda mesmo com exp válido) e saudável.
"""

from app.jobs.checar_cookie import ALERTA_DAYS, checar_expiracao_cookie
from app.services.painel_ope_client import AuthenticationError


class _FakeClient:
    def __init__(self, dias=10, semanatec_ok=True):
        self.dias = dias
        self._ok = semanatec_ok
        self.get_semanatec_calls = 0

    def dias_para_expirar(self):
        if self.dias == "invalido":
            raise AuthenticationError("cookie sem payload JSON")
        return self.dias

    def get_semanatec(self, **kwargs):
        self.get_semanatec_calls += 1
        if not self._ok:
            raise AuthenticationError("semanatec respondeu HTTP 401")


def _monkey(monkeypatch, settings_val, client_fake):
    monkeypatch.setattr(
        "app.jobs.checar_cookie.settings.ope_session_cookie", settings_val, raising=False
    )
    monkeypatch.setattr("app.jobs.checar_cookie.PainelOpeClient", lambda: client_fake)
    mensagens = []
    monkeypatch.setattr(
        "app.jobs.checar_cookie.avisar_telegram", lambda msg: mensagens.append(msg)
    )
    return mensagens


class TestChecarExpiracaoCookie:
    def test_cookie_ausente(self, monkeypatch):
        msgs = _monkey(monkeypatch, None, _FakeClient())
        checar_expiracao_cookie()
        assert msgs and "ausente" in msgs[0]

    def test_cookie_invalido_parse(self, monkeypatch):
        msgs = _monkey(monkeypatch, "algum.cookie", _FakeClient(dias="invalido"))
        checar_expiracao_cookie()
        assert msgs and "inválido" in msgs[0]

    def test_sessao_invalidada_no_servidor(self, monkeypatch):
        # exp válido (10 dias) mas /semanatec 401 → alerta imediato.
        msgs = _monkey(monkeypatch, "algum.cookie", _FakeClient(dias=10, semanatec_ok=False))
        checar_expiracao_cookie()
        assert msgs and "invalidada no servidor" in msgs[0]

    def test_saudavel_sem_alerta(self, monkeypatch):
        msgs = _monkey(monkeypatch, "algum.cookie", _FakeClient(dias=10, semanatec_ok=True))
        checar_expiracao_cookie()
        assert msgs == []

    def test_perto_de_expirar_alerta(self, monkeypatch):
        msgs = _monkey(monkeypatch, "algum.cookie", _FakeClient(dias=ALERTA_DAYS, semanatec_ok=True))
        checar_expiracao_cookie()
        assert msgs and "expira em" in msgs[0]

    def test_sonda_server_eh_chamada_quando_saudavel(self, monkeypatch):
        fake = _FakeClient(dias=10, semanatec_ok=True)
        _monkey(monkeypatch, "algum.cookie", fake)
        checar_expiracao_cookie()
        assert fake.get_semanatec_calls == 1