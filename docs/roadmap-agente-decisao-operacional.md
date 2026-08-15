# Roadmap — Agente de apoio à decisão operacional (v3)

> Terceira revisão. As duas primeiras assumiam ingestão manual pesada; a investigação nesta conversa revelou quatro fontes reais, sendo a mais importante um client Python **que você já construiu e já roda em produção local** (`proxxima_client.py`, autenticação ASP.NET completa com token anti-forgery). O trabalho deixou de ser "construir integrações do zero" e passou a ser "portar o que já funciona pro backend centralizado".

**Objetivo do produto:** um agente consultivo (Gemini + OpenCode) que cruza dados de recorrência, produtividade, banco de horas/HE, infrações e inspeção — para responder perguntas e gerar relatórios sem você precisar abrir tela por tela.

**Modo de operação nessa fase:** puramente consultivo. Sem ações automáticas, sem autonomia — só leitura, cruzamento e geração de relatório.

---

## As quatro fontes reais

### 1. `Painel_ServicosApi/GetAll` (Proxxima Connect) — a fonte principal

```
POST https://proxxima.sinapseinformatica.com.br/Proxxima/Web/Aniel.Connect/api/Painel_ServicosApi/GetAll
```
Autenticação: login ASP.NET Forms (token anti-forgery + cookie de sessão + cookie de autenticação). **Você já tem um client Python testado e funcionando** (`proxxima_client.py`) que resolve login, extração de token, e reautenticação automática em caso de expiração — ele será portado, não reescrito.

Traz serviços **abertos e fechados**, controlado por `lookback_days` (você já usa 30 dias no app local). Cada registro tem `os`, `tecnico`, `status`, `nat`, `uni`, `abertura`, `venc`, `slaTxt`, `relatos`, entre outros — é a fonte mais granular e completa, e a única com **atribuição de técnico por serviço**.

**Isso é o que resolve o cruzamento de recorrência por pessoa** (ver fonte 3, abaixo).

### 2. `painel-ope` (Vercel) — banco de horas, HE e infrações

```
POST https://painel-ope.vercel.app/api/analises   {de, ate, setor}
POST https://painel-ope.vercel.app/api/semanatec  {setor}
```
Autenticação via cookie de sessão (`ope_session`), validade ~7 dias (JWT com `exp` embutido). `analises` retorna rankings já calculados: `rankPontBaixa`, `rankTecHE`, `recorrentesHE`, `oddPorSupervisor`, `cardsUnidadeHE`, `rankSupHE`, `infracoesListaSemana`. `semanatec` retorna a lista de nomes de técnicos ativos no setor — serve como validador.

**Ponto de atenção:** renovação manual do cookie a cada ~7 dias.

### 3. Recorrência — export manual (Excel "Analítico") + join com o GetAll

Baixado periodicamente (quase diário) do painel — sem API própria. Estrutura real, por protocolo:

```
Protocolo | Data abertura | Data fechamento | Problema do fechamento | Cidade | Unidade | Etiqueta |
Protocolo anterior | Data abertura anterior | Data fechamento anterior | Problema do fechamento anterior |
Dias entre as OS | É recorrência?
```

Já vem com a cadeia de recorrência calculada (liga cada OS à sua anterior dentro de 30 dias) — mas **sem coluna de técnico**. A atribuição de técnico vem do join `Protocolo` (aqui) = `os` (no GetAll, fonte 1), pegando o campo `tecnico` de lá.

### 4. Inspeção — único domínio 100% manual

Google Sheets: `tecnico | data_inspecao | pontuacao | criterios_reprovados | inspetor`. Volume baixo (35 técnicos, amostragem por risco).

**`aniel-aovivo` (webhook n8n) deixa de ser fonte principal** — os campos que ele agregava (`reabriuHoje`, `fechProd`, `fechImprod`) já são cobertos com mais detalhe pelo GetAll + Excel de recorrência. Fica como opcional, útil só se você quiser um resumo visual rápido sem esperar o pipeline processar.

---

## Stack

- Backend de agregação: **FastAPI** + **PostgreSQL**
- `ProxximaClient` — **portado do seu app local existente**, não reescrito, rodando como job síncrono agendado (não dentro dos endpoints async)
- `PainelOpeClient` (cookie) via `httpx`
- Recorrência: ingestão do Excel (`pandas`/`openpyxl`) + enriquecimento via join com `ProxximaClient.fetch_servicos()`
- Inspeção: **Google Sheets API** (`gspread` + service account)
- Agente: **OpenCode** (plugin TypeScript) chamando **Gemini** via function calling
- Relatórios: **python-docx**
- Agendamento: **APScheduler**
- Alertas de manutenção: **Telegram bot**
- **Segredos**: usuário/senha do Proxxima e cookie do `painel-ope` vão em variáveis de ambiente / secrets manager — nunca hardcoded, nunca versionado em git

---

## Sprint 0 — Fechar o schema definitivo (2–3 dias)

Esse sprint ficou mais curto que na v1, porque grande parte da investigação já foi feita nesta conversa.

**Tarefas**
1. Mapear os campos exatos de `resumo` e `semana` do `aniel-aovivo` que viram colunas no Postgres (backlog, aberturas, fechamentos produtivos/improdutivos, reaberturas — por unidade, natureza e dia).
2. Mapear os campos de `analises` do `painel-ope` que interessam (rankings de HE, infrações, saldo por supervisor/unidade).
3. Confirmar a janela de datas aceita por `analises`/`semanatec` (testar `de`/`ate` com intervalos maiores, ver se aceita mês inteiro ou só semana).
4. Desenhar o schema do Postgres: tabelas `solicitacao_resumo_diario`, `metrica_recorrencia_diaria`, `metrica_produtividade_diaria` (todas populadas via `aniel-aovivo`), `banco_horas_semanal`, `infracao` (via `painel-ope`), e `inspecao` (via Sheets).
5. Criar a conta de serviço do Google Sheets (só necessária agora pra Inspeção).
6. Testar manualmente decodificar o cookie `ope_session` (é um JWT em base64) pra confirmar a lógica de expiração e montar o alerta de renovação.

**Critério de pronto:** schema fechado, e você validou que os campos batem com o que via manualmente nos dois painéis.

---

## Sprint 1 — Fundação + `aniel-aovivo` (1 semana)

**Tarefas**
1. Criar o projeto FastAPI (`app/models`, `app/schemas`, `app/routers`, `app/services`).
2. **Portar `proxxima_client.py`** do seu app local pra `app/services/proxxima_client.py` — sem reescrever a lógica de login/reautenticação, só adaptar imports e configuração (usuário/senha via variável de ambiente em vez do `config.py` local com JSON).
3. Job síncrono agendado (APScheduler, não dentro dos endpoints async) que chama `fetch_servicos(lookback_days=30)` periodicamente (ex: a cada 30 min, mesmo `refresh_interval` que você já usa) e grava no Postgres.
4. Endpoints de leitura (async, só consultam o Postgres já sincronizado): `GET /solicitacoes/resumo?unidade=`, `GET /solicitacoes/por-tecnico?tecnico=`.

**Exemplo de código — job de sync usando o client portado**

```python
# app/jobs/sync_proxxima.py
from app.services.proxxima_client import ProxximaClient  # portado do app local
from app.config import PROXXIMA_USER, PROXXIMA_PASSWORD

def sync_servicos(db):
    client = ProxximaClient(usuario=PROXXIMA_USER, senha=PROXXIMA_PASSWORD)
    servicos = client.fetch_servicos(lookback_days=30)  # já existe no seu código

    for s in servicos:
        registro = SolicitacaoServico(
            os=s["os"].split("/")[0],
            unidade=s["uni"],
            natureza=s["nat"],
            status=s["status"],
            tecnico=s.get("tecnico"),
            abertura=_parse_data_br(s["abertura"]),
            venc=_parse_data_br(s.get("venc")),
            sla_status=s.get("slaTxt"),
        )
        db.merge(registro)
    db.commit()
    print(f"[proxxima] {len(servicos)} serviços sincronizados")
```

**Exemplo de código — endpoint por técnico (habilitado pelo campo que faltava antes)**

```python
# app/routers/solicitacoes.py
@router.get("/por-tecnico")
async def solicitacoes_por_tecnico(tecnico: str, db=Depends(get_db)):
    registros = await buscar_solicitacoes_por_tecnico(db, tecnico)
    return {
        "tecnico": tecnico,
        "total": len(registros),
        "abertos": sum(1 for r in registros if r.status != "Encerrada"),
        "detalhe": registros,
    }
```

**Critério de pronto:** `GET /solicitacoes/por-tecnico?tecnico=SILVANILDO%20RODRIGUES%20DA%20SILVA` retorna os serviços dele, batendo com o que aparece no painel original.

---

## Sprint 2 — `painel-ope`: banco de horas, HE e infrações (1 semana)

**Tarefas**
1. Implementar `PainelOpeClient` com o cookie vindo de variável de ambiente.
2. Função de decodificação do JWT do cookie pra saber a data de expiração e disparar alerta preventivo (ex: 1 dia antes de vencer).
3. Endpoints: `GET /banco-horas/analises?setor=&de=&ate=`, `GET /banco-horas/roster?setor=`.
4. Tratamento de erro 401/403 → aviso via Telegram pedindo renovação do cookie.

**Exemplo de código — client com verificação de expiração**

```python
# app/services/painel_ope_client.py
import httpx, base64, json
from datetime import datetime, timezone

class PainelOpeClient:
    BASE_URL = "https://painel-ope.vercel.app/api"

    def __init__(self, cookie_session: str):
        self.cookie = cookie_session
        self.headers = {"Content-Type": "application/json", "Cookie": f"ope_session={cookie_session}"}

    def dias_para_expirar(self) -> int:
        payload_b64 = self.cookie.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        return (exp - datetime.now(timezone.utc)).days

    async def get_analises(self, de: str, ate: str, setor: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{self.BASE_URL}/analises", headers=self.headers,
                                      json={"de": de, "ate": ate, "setor": setor})
            resp.raise_for_status()
            return resp.json()

    async def get_roster(self, setor: str) -> list[str]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{self.BASE_URL}/semanatec", headers=self.headers, json={"setor": setor})
            resp.raise_for_status()
            return resp.json()["tecnicos"]
```

**Exemplo de código — checagem diária de expiração**

```python
# app/jobs/checar_cookie.py
async def checar_expiracao_cookie():
    client = PainelOpeClient(cookie_session=os.environ["OPE_SESSION_COOKIE"])
    dias = client.dias_para_expirar()
    if dias <= 1:
        await avisar_telegram(f"⚠️ Cookie do painel-ope expira em {dias} dia(s). Renove em painel-ope.vercel.app.")
```

**Critério de pronto:** `GET /banco-horas/analises?setor=REG02&de=20260810&ate=20260816` retorna os mesmos números do dashboard, e o job de checagem de expiração roda diariamente.

---

## Sprint 3 — Recorrência (Excel + join) e Inspeção (Sheets) (1 semana)

Dois domínios manuais, tratados de formas diferentes: recorrência precisa de enriquecimento (join), inspeção é direta.

**Tarefas**
1. ETL do Excel de recorrência: ler o "Analítico", normalizar colunas.
2. Enriquecer com técnico via join `Protocolo` = `os` (usando os dados já sincronizados do `ProxximaClient` no Postgres, sem precisar chamar a API de novo).
3. Gravar em `ocorrencia_recorrencia` (uma linha por protocolo, incluindo o flag `é_recorrencia` e o `tecnico` resolvido).
4. Aba `Inspecao` no Sheets + `SheetsClient` (mesmo padrão já usado antes).
5. Endpoint `GET /recorrencia/por-tecnico?tecnico=&periodo=` — conta quantos protocolos daquele técnico têm `é_recorrencia = SIM` no período.

**Exemplo de código — ETL de recorrência com enriquecimento**

```python
# app/etl/recorrencia.py
import pandas as pd

def importar_recorrencia(caminho_excel: str, db):
    df = pd.read_excel(caminho_excel, sheet_name="Analitico", header=1)
    df.columns = [c.strip() for c in df.columns]

    # busca o mapa protocolo -> técnico direto do Postgres (já sincronizado pelo ProxximaClient)
    mapa_tecnico = _buscar_mapa_protocolo_tecnico(db)

    linhas_importadas = 0
    for _, row in df.iterrows():
        protocolo = str(row["Protocolo"])
        registro = OcorrenciaRecorrencia(
            protocolo=protocolo,
            unidade=row["Unidade"],
            cidade=row["Cidade"],
            problema_fechamento=row["Problema do fechamento"],
            protocolo_anterior=str(row["Protocolo anterior"]) if pd.notna(row["Protocolo anterior"]) else None,
            dias_entre_os=row["Dias entre as OS"] if pd.notna(row["Dias entre as OS"]) else None,
            e_recorrencia=(row["É recorrência?"] == "SIM"),
            tecnico=mapa_tecnico.get(protocolo),  # pode vir None se o protocolo não estiver no lookback do GetAll
        )
        db.merge(registro)
        linhas_importadas += 1

    db.commit()
    sem_tecnico = sum(1 for _, r in df.iterrows() if str(r["Protocolo"]) not in mapa_tecnico)
    print(f"[recorrencia] {linhas_importadas} importadas, {sem_tecnico} sem técnico resolvido (fora do lookback)")
```

**Ponto de atenção:** como o `GetAll` usa `lookback_days` (30 dias), protocolos mais antigos que isso no Excel de recorrência podem não ter técnico resolvido pelo join. Se isso acontecer com frequência, vale aumentar o `lookback_days` do sync ou manter um histórico maior no Postgres em vez de depender só da janela do GetAll.

**Critério de pronto:** rodar a importação com o arquivo real e conferir que a maioria dos protocolos teve técnico resolvido — poucos "sem técnico" é esperado (protocolos fora da janela), muitos é sinal de problema no join.

---

## Sprint 4 — Endpoints de cruzamento (1 semana)

O coração do valor — juntar as três fontes num payload só, por técnico ou por unidade.

**Exemplo de código — diagnóstico do técnico cruzando as 3 fontes**

```python
# app/routers/diagnostico.py
@router.get("/diagnostico-tecnico/{nome_tecnico}")
async def diagnostico_tecnico(nome_tecnico: str, periodo_de: str, periodo_ate: str, db=Depends(get_db)):
    recorrencia_prod = await buscar_metricas_aniel(db, nome_tecnico, periodo_de, periodo_ate)
    banco_horas = await buscar_banco_horas(db, nome_tecnico, periodo_de, periodo_ate)
    inspecao = await buscar_ultima_inspecao(db, nome_tecnico)

    return {
        "tecnico": nome_tecnico,
        "recorrencia_reaberturas": recorrencia_prod["reabriu_total"],
        "produtividade": recorrencia_prod["fech_prod_total"],
        "improdutividade": recorrencia_prod["fech_improd_total"],
        "he_horas": banco_horas.get("heHoras"),
        "infracoes": banco_horas.get("infrDias"),
        "ultima_inspecao": inspecao,
        "alerta": _calcular_alerta(recorrencia_prod, banco_horas, inspecao),
    }

def _calcular_alerta(rec_prod, banco_horas, inspecao) -> list[str]:
    alertas = []
    if rec_prod["reabriu_total"] > LIMITE_REABERTURA:
        alertas.append("recorrência de reabertura acima do limite")
    if banco_horas.get("heHoras", 0) > LIMITE_HE_SEMANAL:
        alertas.append("HE acima do limite semanal")
    if inspecao and inspecao["pontuacao"] < META_INSPECAO:
        alertas.append("pontuação de inspeção abaixo da meta")
    return alertas
```

Também criar `GET /status-unidade/{unidade}` (backlog + HE + recorrência agregados) e `GET /comparativo-unidades` (Campina Grande vs Lagoa Seca), seguindo o mesmo padrão de junção.

**Nota importante:** como `aniel-aovivo` e `painel-ope` usam **nome completo em maiúsculas** como chave (não IDs numéricos), padronize isso em todo o sistema — inclusive na aba `Inspecao` do Sheets. Use `semanatec` como validador: antes de gravar qualquer registro, confira se o nome bate com o roster retornado por ele.

**Critério de pronto:** rodar o diagnóstico pra um técnico que você já sabe que está com problema (recorrência ou HE) e ver o alerta disparar corretamente.

---

## Sprint 5 — O agente: tools no OpenCode + Gemini (1 semana)

Igual ao desenho original, agora as tools apontam pros endpoints de cruzamento já validados no Sprint 4.

```typescript
// opencode-plugin-operacoes/index.ts
import { tool } from "@opencode-ai/plugin";

const API_BASE = process.env.OPS_API_URL ?? "http://localhost:8000";

async function chamarApi(path: string) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API respondeu ${res.status}`);
  return res.json();
}

export const getDiagnosticoTecnico = tool({
  description: "Diagnóstico completo de um técnico: recorrência, produtividade, HE, infrações e inspeção",
  args: {
    nome_tecnico: tool.schema.string(),
    periodo_de: tool.schema.string().describe("formato YYYYMMDD"),
    periodo_ate: tool.schema.string().describe("formato YYYYMMDD"),
  },
  async execute({ nome_tecnico, periodo_de, periodo_ate }) {
    return chamarApi(`/diagnostico-tecnico/${encodeURIComponent(nome_tecnico)}?periodo_de=${periodo_de}&periodo_ate=${periodo_ate}`);
  },
});

export const getStatusUnidade = tool({
  description: "Status atual de uma unidade: backlog, HE, recorrência e produtividade",
  args: { unidade: tool.schema.string() },
  async execute({ unidade }) {
    return chamarApi(`/status-unidade/${encodeURIComponent(unidade)}`);
  },
});

export const getComparativoUnidades = tool({
  description: "Compara unidades lado a lado num período",
  args: { periodo_de: tool.schema.string(), periodo_ate: tool.schema.string() },
  async execute({ periodo_de, periodo_ate }) {
    return chamarApi(`/comparativo-unidades?periodo_de=${periodo_de}&periodo_ate=${periodo_ate}`);
  },
});
```

**Critério de pronto:** perguntas em linguagem natural ("quem em Campina Grande está com recorrência alta essa semana?") retornam respostas coerentes com os endpoints.

---

## Sprint 6 — Relatórios automáticos (3–5 dias)

Mesma lógica da v1 — tool `gerar_relatorio_semanal` usando `python-docx`, agora alimentada pelas três fontes já cruzadas no Sprint 4.

---

## Sprint 7 — Robustez (1 semana)

**Tarefas**
1. Agendar sync do `ProxximaClient` (ex: a cada 30 min, mesmo `refresh_interval` do app local) e do `painel-ope` (menos frequente, ex: diário, pra não gastar chamadas numa fonte que pode expirar).
2. Alerta Telegram já implementado no Sprint 2 — testar cenário real de expiração, tanto do cookie do `painel-ope` quanto de falha de login do `ProxximaClient`.
3. Testes (`pytest`) principalmente em `_calcular_alerta`, no parser do Excel de recorrência, e no join protocolo↔técnico (é o ponto mais sensível a mudança de formato).
4. Avaliar recurso da EC2 — agora rodando MI-IA + Sistema CTOs + este novo serviço com dois clients autenticados.

---

## Segurança das credenciais

Duas credenciais sensíveis nesse projeto — usuário/senha do Proxxima e cookie do `painel-ope`. Ambas devem:
- Ficar em variáveis de ambiente (`.env` fora do controle de versão) ou num secrets manager (AWS Secrets Manager, já que está na mesma infra da EC2)
- Nunca aparecer em logs, prints de debug, ou mensagens/chats — se uma credencial real acabar exposta em algum lugar (mesmo que não público), o mais seguro é trocá-la depois
- Se possível, usar um **usuário de serviço dedicado** no Proxxima para essa integração, em vez do seu login pessoal — separa "você usando o sistema" de "automação usando o sistema", e evita que uma troca de senha sua quebre o pipeline

---

## Resumo do cronograma

| Sprint | Duração | Entrega principal |
|---|---|---|
| 0 | 2–3 dias | Schema fechado com base nos payloads reais |
| 1 | 1 semana | `ProxximaClient` portado e integrado (solicitações abertas/fechadas + técnico por OS) |
| 2 | 1 semana | `painel-ope` integrado (banco de horas, HE, infrações) + alerta de cookie |
| 3 | 1 semana | Recorrência (Excel + join de técnico) e Inspeção (Sheets) |
| 4 | 1 semana | Endpoints de cruzamento |
| 5 | 1 semana | Agente funcionando com tools reais |
| 6 | 3–5 dias | Relatório automático |
| 7 | 1 semana | Robustez: agendamento, alertas, testes |

**Total estimado: ~6–7 semanas.** O maior ganho desta versão não é tempo — é risco: a parte mais incerta de qualquer integração (autenticação) já está resolvida e testada em produção local, restando só o trabalho de portar e centralizar. Os dois pontos de manutenção humana recorrente (cookie do `painel-ope` a cada ~7 dias, e o download manual do Excel de recorrência quase diário) já têm alerta ou já fazem parte da sua rotina atual.

---

## Pontos em aberto

1. Confirmar se `analises`/`semanatec` (painel-ope) aceitam intervalos maiores que uma semana, útil pra relatórios mensais.
2. Decidir se vale aumentar o `lookback_days` do `ProxximaClient` além de 30 dias, considerando que o Excel de recorrência é baixado quase diariamente e pode conter protocolos mais antigos que a janela padrão.
