"""Cliente de sincronização com o Proxxima Connect.

Portado do app local ``proxxima-dashboard`` (``app/proxxima_client.py``).
A lógica de autenticação, extração do token anti-forgery e paginação do
``Painel_ServicosApi/GetAll`` foi preservada — mudou apenas a origem da
configuração: credenciais agora vêm de variáveis de ambiente (via
``app.config``) em vez do JSON local do dashboard.

Fluxo de autenticação e coleta:

1. ``GET`` na página de login para obter o cookie de sessão e o
   ``__RequestVerificationToken`` (anti-forgery do ASP.NET MVC).
2. ``POST`` (form urlencoded) com usuário/senha para autenticar a sessão.
3. ``POST`` em ``Painel_ServicosApi/GetAll`` paginado (como o DataTables do
   painel), restringindo a consulta pela janela ``lookback_days``.

Uso típico::

    from app.services.proxxima_client import ProxximaClient

    client = ProxximaClient(usuario, senha)
    try:
        servicos = client.fetch_servicos(lookback_days=30)
    finally:
        client.close()

Teste manual::

    python -m app.services.proxxima_client 30
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

PROXXIMA_LOGIN_URL = (
    "https://proxxima.sinapseinformatica.com.br/Proxxima/Web/Aniel.Connect/"
    "pt/Account/Login"
)
PROXXIMA_API_URL = (
    "https://proxxima.sinapseinformatica.com.br/Proxxima/Web/Aniel.Connect/"
    "api/Painel_ServicosApi/GetAll"
)

DEFAULT_LOOKBACK_DAYS = 30

LOGIN_PATH = "/Account/Login"

# Página do painel (base usada também como Referer nas chamadas da API).
PANEL_PAGE_URL = urljoin(PROXXIMA_LOGIN_URL, "../Painel_Servicos")
PANEL_MARKERS = ("Painel_ServicosApi", "Painel de Servi")

INPUT_TAG_RE = re.compile(r"<input[^>]*>", re.IGNORECASE)
TOKEN_INPUT_RE = re.compile(
    r"<input[^>]*name\s*=\s*[\"']__RequestVerificationToken[\"'][^>]*>",
    re.IGNORECASE,
)

DEFAULT_USERNAME_FIELDS = ("Username", "UserName", "Usuario", "Login", "Email")
DEFAULT_PASSWORD_FIELDS = ("Password", "Senha")

# Colunas do DataTables do Painel de Serviços, na mesma ordem usada pela
# página (a coluna 0 é o checkbox, sem dado).
COLUMNS_DATA: tuple[str, ...] = (
    "",
    "numero_Obra_Original",
    "equipe_Matricula",
    "num_Doc",
    "numero_Cliente",
    "cpf_Cnpj_Cliente",
    "id_Venda",
    "id_Atendimento",
    "status_Execucao",
    "responsabilidade",
    "responsavel",
    "pontos_Previstos",
    "pontos_Realizados",
    "tipo_Servico",
    "subTipo_Servico",
    "sla",
    "tipo_Imovel",
    "supervisor",
    "grupo_Area",
    "area",
    "localidade",
    "nome_Cliente",
    "endereco_Cliente",
    "endereco_Numero",
    "endereco_Complemento",
    "endereco_Bairro",
    "endereco_Cidade",
    "endereco_UF",
    "endereco_Pais",
    "telefone_Principal_Cliente",
    "celular_Cliente",
    "usuario_Abertura_OS",
    "dataHora_Abertura_OS",
    "dataHora_Abertura_OS_Original",
    "usuario_Agendamento_OS",
    "data_Hora_Agendamento_OS",
    "dataHora_Deslocamento_OS",
    "dataHora_IniAtendimento_OS",
    "dataHora_Pausou_OS",
    "dataHora_Reinicio_OS",
    "dataHora_FimAtendimento_OS",
    "descricao_Encerramento",
    "status_Auditoria",
    "usuario_Encerramento",
    "dataHora_Encerramento_OS",
    "dataHora_Vencimento_OS",
    "atendimento_Finalizado",
    "codCt",
    "projeto",
    "categoriaCliente",
    "monitor",
    "natureza",
    "planoProduto",
    "periodo",
    "observacao",
    "observacao_Pausa",
    "observacaoTeste",
    "latitudeLongitude",
    "seq",
    "wo",
    "temOsDigital",
    "departamento",
    "tipo_Prioridade",
    "status_Cobranca",
    "segmento",
    "equipe_Auxiliares",
)

# Filtros enviados pelo painel na chamada ao GetAll (valores padrão).
DEFAULT_FILTERS: dict[str, Any] = {
    "Id_Venda": "",
    "ExibirSomenteOSComVenda": "false",
    "Id_Modelo": "",
    "StatusOS": "",
    "Status_Cobranca": "",
    "StatusEquipe": "",
    "IdPeriodo": "",
    "Id_Natureza": "",
    "Pais": "Brasil",
    "Estado": "",
    "Cidade": "",
    "Bairro": "",
    "Contrato": "",
    "Projeto": "",
    "Id_Tipo_Servico": "",
    "Id_Sub_Tipo_Servico": "",
    "Matricula_Equipe": "",
    "Id_Supervisor": "",
    "Id_Monitor": "",
    "Grupo_Area": "",
    "Area": "",
    "Localidade": "",
    "SituacaoOS": "",
    "Status_Auditoria": "",
    "Sla": "",
    "TipoPrioridade": "",
    "Responsabilidade": "",
    "TemOsDigital": "",
    "CategoriaCliente": "",
    "CodDepto": "",
    "StatusSla": "",
    "UsuarioCriacao": "",
    "Id_Pop": "",
    "Id_Olt": "",
    "Id_ElementoRede": "",
    "Id_Organizacao": "",
    "UtilizaHistoricoReabertura": "false",
}


class ProxximaError(Exception):
    """Erro base do cliente Proxxima."""


class AuthenticationError(ProxximaError):
    """Falha na autenticação ou sessão inválida."""


class ProxximaRequestError(ProxximaError):
    """Falha na comunicação com o Proxxima."""


def _get_attr(tag: str, name: str) -> str | None:
    """Lê o valor de um atributo HTML dentro de uma tag (valor entre aspas)."""
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*([\"'])(.*?)\1",
        tag,
        re.IGNORECASE,
    )
    return match.group(2) if match else None


def _extract_request_verification_token(html: str) -> str:
    """Extrai o ``__RequestVerificationToken`` do HTML da página de login."""
    for tag in TOKEN_INPUT_RE.findall(html):
        value = _get_attr(tag, "value")
        if value is not None:
            return value
    raise AuthenticationError(
        "Não foi possível localizar o campo __RequestVerificationToken "
        "na página de login."
    )


def _extract_inputs(html: str) -> dict[str, dict[str, str]]:
    """Extrai os campos ``<input>`` da página com tipo e valor atuais."""
    inputs: dict[str, dict[str, str]] = {}
    for tag in INPUT_TAG_RE.findall(html):
        name = _get_attr(tag, "name")
        if not name:
            continue
        field_type = (_get_attr(tag, "type") or "text").lower()
        inputs[name] = {
            "type": field_type,
            "value": _get_attr(tag, "value") or "",
        }
    return inputs


def _find_field_by_names(
    inputs: dict[str, dict[str, str]], candidates: tuple[str, ...]
) -> str | None:
    names = list(inputs)
    for candidate in candidates:
        if candidate in names:
            return candidate
    lowered = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _guess_username_field(inputs: dict[str, dict[str, str]]) -> str | None:
    field = _find_field_by_names(inputs, DEFAULT_USERNAME_FIELDS)
    if field:
        return field
    for name in inputs:
        if re.search(r"usuario|user|login|email", name, re.IGNORECASE):
            return name
    return None


def _guess_password_field(inputs: dict[str, dict[str, str]]) -> str | None:
    field = _find_field_by_names(inputs, DEFAULT_PASSWORD_FIELDS)
    if field:
        return field
    for name in inputs:
        if re.search(r"password|passwd|senha|clave", name, re.IGNORECASE):
            return name
    return None


def _build_login_payload(
    html: str,
    username: str,
    password: str,
    username_field: str | None,
    password_field: str | None,
) -> dict[str, str]:
    """Monta o payload do POST de login imitando o envio do formulário."""
    inputs = _extract_inputs(html)
    username_field = username_field or _guess_username_field(inputs) or DEFAULT_USERNAME_FIELDS[0]
    password_field = password_field or _guess_password_field(inputs) or DEFAULT_PASSWORD_FIELDS[0]

    payload: dict[str, str] = {}
    for name, info in inputs.items():
        if "requestverificationtoken" in name.lower():
            payload[name] = info["value"]
        elif name == username_field:
            payload[name] = username
        elif name == password_field:
            payload[name] = password
        elif info["type"] in ("hidden", "checkbox"):
            payload[name] = info["value"]

    payload.setdefault(username_field, username)
    payload.setdefault(password_field, password)
    return payload


class ProxximaClient:
    """Sessão HTTP autenticada no Proxxima Connect."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        username_field: str | None = None,
        password_field: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.username = username
        self.password = password
        self.username_field = username_field
        self.password_field = password_field
        self._authenticated = False

        self.client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
            },
            follow_redirects=True,
            timeout=httpx.Timeout(timeout, read=timeout),
        )

    @staticmethod
    def _is_login_page_url(url: httpx.URL) -> bool:
        return LOGIN_PATH.lower() in url.path.lower()

    def login(self) -> bool:
        """Autentica a sessão. Levanta exceção se não for possível."""
        if self._authenticated:
            return True

        if not self.username or not self.password:
            raise AuthenticationError("Usuário e/ou senha não configurados.")

        try:
            page_response = self.client.get(PROXXIMA_LOGIN_URL)
            page_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProxximaRequestError(
                f"Falha ao acessar a página de login: {exc}"
            ) from exc

        token: str | None = None
        try:
            token = _extract_request_verification_token(page_response.text)
        except AuthenticationError:
            logger.warning(
                "Página de login sem __RequestVerificationToken "
                "(a página mudou? continuando sem o token)."
            )
        payload = _build_login_payload(
            page_response.text,
            self.username,
            self.password,
            self.username_field,
            self.password_field,
        )
        if token:
            payload["__RequestVerificationToken"] = token

        try:
            login_response = self.client.post(PROXXIMA_LOGIN_URL, data=payload)
            login_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProxximaRequestError(
                f"Falha ao enviar as credenciais: {exc}"
            ) from exc

        if self._is_login_page_url(login_response.url):
            raise AuthenticationError(
                "Autenticação recusada: usuário ou senha inválidos."
            )

        self._verify_authenticated_session()
        self._authenticated = True
        logger.info("Sessão autenticada no Proxxima Connect.")
        return True

    def _verify_authenticated_session(self) -> None:
        """Confirma que a sessão consegue abrir o Painel de Serviços."""
        try:
            panel_response = self.client.get(PANEL_PAGE_URL)
            panel_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProxximaRequestError(
                f"Falha ao validar a sessão no Painel de Serviços: {exc}"
            ) from exc

        if self._is_login_page_url(panel_response.url):
            raise AuthenticationError(
                "A sessão não foi aceita (redirecionado de volta ao login)."
            )
        if not any(
            marker.lower() in panel_response.text.lower() for marker in PANEL_MARKERS
        ):
            raise AuthenticationError(
                "A sessão foi criada, mas a página do Painel de Serviços "
                "não foi reconhecida."
            )

    def fetch_servicos(
        self,
        *,
        lookback_days: int | None = None,
        data_inicial: date | None = None,
        data_final: date | None = None,
        tipo_data: str = "1",
        page_size: int = 500,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        """Busca todas as OS do Painel de Serviços dentro da janela de consulta.

        ``tipo_data`` segue o enum da tela: 0=agendamento, 1=criação,
        2=encerramento, 3=vencimento, 4=sem agendamento.
        """
        if not self._authenticated:
            self.login()

        if data_inicial is None or data_final is None:
            days = lookback_days if lookback_days is not None else DEFAULT_LOOKBACK_DAYS
            today = date.today()
            if data_inicial is None:
                data_inicial = today - timedelta(days=days)
            if data_final is None:
                data_final = today

        servicos: list[dict[str, Any]] = []
        draw = 1
        start = 0
        total: int | None = None

        while True:
            params = self._build_get_all_params(
                data_inicial=data_inicial,
                data_final=data_final,
                tipo_data=tipo_data,
                start=start,
                length=page_size,
                draw=draw,
            )
            records, records_total = self._call_get_all(params)

            servicos.extend(records)
            total = records_total if total is None else total
            start += len(records)
            draw += 1

            if not records or start >= total:
                break
            if draw > max_pages:
                logger.warning(
                    "Sincronização interrompida após %d páginas "
                    "(possível paginação infinita).",
                    max_pages,
                )
                break

        logger.info("Sincronizados %d serviços do Proxxima.", len(servicos))
        return servicos

    def _build_get_all_params(
        self,
        *,
        data_inicial: date,
        data_final: date,
        tipo_data: str,
        start: int,
        length: int,
        draw: int,
    ) -> dict[str, Any]:
        """Monta o corpo do POST do GetAll igual ao DataTables do painel."""
        params: dict[str, Any] = {
            "draw": str(draw),
            "start": str(start),
            "length": str(length),
            "search[value]": "",
            "search[regex]": "false",
            "order[0][column]": "1",
            "order[0][dir]": "desc",
        }
        for index, data_name in enumerate(COLUMNS_DATA):
            params[f"columns[{index}][data]"] = data_name
            params[f"columns[{index}][name]"] = ""
            params[f"columns[{index}][searchable]"] = "true"
            params[f"columns[{index}][orderable]"] = "true"
            params[f"columns[{index}][search][value]"] = ""
            params[f"columns[{index}][search][regex]"] = "false"

        params.update(DEFAULT_FILTERS)
        params["TipoData"] = tipo_data
        params["DataInicial"] = data_inicial.strftime("%d/%m/%Y")
        params["DataFinal"] = data_final.strftime("%d/%m/%Y")
        return params

    def _call_get_all(
        self, params: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int]:
        """Executa uma página do Painel_ServicosApi/GetAll e retorna (OS, total)."""
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": PANEL_PAGE_URL,
        }
        try:
            response = self.client.post(PROXXIMA_API_URL, data=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ProxximaRequestError(
                f"Falha na chamada a Painel_ServicosApi/GetAll: {exc}"
            ) from exc

        if response.status_code == 401 or self._is_login_page_url(response.url):
            self._authenticated = False
            raise AuthenticationError(
                "Sessão expirada. Reautentique antes de sincronizar."
            )

        if response.status_code != 200:
            raise ProxximaRequestError(
                f"Painel_ServicosApi/GetAll respondeu HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProxximaRequestError(
                "Resposta de Painel_ServicosApi/GetAll não é JSON válido "
                "(a sessão pode ter expirado ou o endpoint mudou)."
            ) from exc

        if not isinstance(payload, dict) or "data" not in payload:
            raise ProxximaRequestError(
                "Resposta de Painel_ServicosApi/GetAll sem a chave 'data'."
            )

        records = payload.get("data") or []
        records_total = (
            payload.get("recordsTotal")
            or payload.get("recordsFiltered")
            or len(records)
        )
        return list(records), int(records_total)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ProxximaClient:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def sync_painel_servicos(
    username: str | None = None,
    password: str | None = None,
    lookback_days: int | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Sincroniza o painel usando as credenciais de configuração (.env)."""
    cred_user = username if username is not None else settings.proxxima_user
    cred_password = password if password is not None else settings.proxxima_password
    with ProxximaClient(cred_user, cred_password) as client:
        return client.fetch_servicos(lookback_days=lookback_days, **kwargs)


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    days = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOOKBACK_DAYS
    results = sync_painel_servicos(lookback_days=days)
    print(f"{len(results)} serviços sincronizados.")
