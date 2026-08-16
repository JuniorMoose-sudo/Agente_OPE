# Progresso — Agente de apoio à decisão operacional

Última atualização: 2026-08-16

## Sprint 7 — Robustez

Status: **concluído** (testes pytest expandidos de 31 para 82; commit pendente).

### Feito

- `tests/test_cruzamento.py` (novos):
  - `TestNormalizarUnidade` — 10 testes cobrindo prefixo `REG-`, `UNIDADE `, sufixo `| PB`, case insensitivity, None/vazio, espaços extras.
  - `TestIsAberta` — 11 testes cobrindo todos os status reais (Aberta, Fechada Produtiva/Improdutiva, Cancelado, None, vazio).
  - `TestDeltaStr` — 4 testes: igual, aumento, queda, zero→algo.
  - `TestDeltaPct` — 5 testes: igual, +50%, -50%, anterior zero com algo, ambos zero.
- `tests/test_relatorio.py` (novos):
  - `TestAddTitulo`, `TestAddSubsecao`, `TestAddParagrafo`, `TestAddTabela`, `TestEnsureDir` — helpers de formatação.
  - `TestLogicaCalculo` — lógica de cálculo de taxa produtividade, concentração top 3, e deltas de tendência.
  - `TestIsAbertaRelatorio` — `_is_aberta` do módulo relatorio (diferente do sync_proxxima).
  - `TestConstantesAlerta` — constantes LIMITE_REABERTURA=1, LIMITE_HE_SEMANAL=8.0, META_INSPECAO=7.0.
- pytest: **82 passed** (31 existentes + 51 novos).

### Observações sobre scheduling

O agendamento (APScheduler) já está implementado nos Sprints 1 e 2:
- `sync_proxxima`: 30 minutos via lifespan (`app/main.py`).
- `sync_painel_ope`: diário via lifespan.
- `checar_cookie`: diário via lifespan.
Todos os three jobs estão ativos quando o uvicorn sobe. Não é necessário implementar scheduling adicional no Sprint 7.

### Pendências

- **Integração TOTVS Analytics (GoodData)** — aguarda payload+response do F12 do usuário para mapear a API. Detalhes no plano de execução.
- **Testes com DB real (SQLite em memória)** — adicionar fixtures SQLAlchemy para testar queries de `cruzamento.py` e `relatorio.py` contra banco de teste.

## Sprint 6 — Relatórios automáticos

Status: **concluído** (relatório rico 10 seções gerado com sucesso, commit `184bb57`).

### Feito

- `app/models/relatorio.py`: modelo `Relatorio` (id, titulo, unidade, periodo_de, periodo_ate, nome_arquivo, caminho, criado_em). Tabela criada automaticamente via `Base.metadata.create_all` no lifespan.
- `app/services/relatorio.py`: `gerar_relatorio_semanal()` — relatório rico 10 seções com python-docx:
  1. **Resumo Executivo** com KPIs (backlog, fechadas, HE, infrações, recorrências) + variação vs período anterior.
  2. **Análise de Tendências** — insights automáticos (backlog cresceu? produtividade caiu? HE acima do esperado?).
  3. **Produtividade por Técnico** — abertas, produtivas, improdutivas, canceladas, total, taxa de produtividade; destaque melhor/pior.
  4. **Recorrência por Técnico** — protocolos, reaberturas, taxa, concentração top 3.
  5. **Horas Extras por Técnico** — ranking com totais.
  6. **Distribuição por Natureza** — com percentuais.
  7. **Distribuição por Dia da Semana** — padrões temporais (dia alto/baixo).
  8. **Risco Combinado** — técnicos com HE **e** recorrência simultaneamente (cruzamento de fontes).
  9. **Protocolos com Recorrência** — detalhe por protocolo: técnico, problema de fechamento, dias entre OS.
  10. **Observações e Fontes** — timestamp de geração.
  - Compara automaticamente com período anterior (mesma duração, janela deslizante).
  - Helpers: `_delta_str`, `_delta_pct`, `_addSubsecao`, `_addParagrafos`, `_is_aberta`.
  - Queries DB: `_buscar_produtividade_por_tecnico`, `_buscar_naturezas`, `_buscar_distribuicao_dia_semana`, `_buscar_top_protocolos_recorrentes`, `_buscar_tecnicos_com_he_e_recorrencia`.
- `app/routers/relatorio.py`:
  - `POST /relatorios` — gera relatório (body: `{unidade, periodo_de, periodo_ate}`). Retorna metadados + ID.
  - `GET /relatorios/{id}` — metadados do relatório.
  - `GET /relatorios/{id}/download` — download do `.docx` via `FileResponse` (sem auth — viabiliza download direto pelo navegador).
- Plugin `.opencode/plugins/operacoes.ts`: tool `getRelatorioSemanal` — chama `POST /relatorios`, retorna ID + `download_url`.
- Agent `.opencode/agent/operacoes.md`: seção "Relatórios" adicionada ao prompt.
- `app/main.py`: router `relatorio` registrado; `Base.metadata.create_all(engine)` no lifespan.
- `app/config.py`: nova opção `dir_relatorios` (padrão `relatorios`).
- `.env.example`: `DIR_RELATORIOS=relatorios` documentado.
- `.gitignore`: `relatorios/` adicionado.
- `requirements.txt`: `python-docx>=1.1` adicionado.
- pytest: 82 passed (31 existentes + 51 novos em Sprint 7).
- **Validado com sucesso**: relatório ID 3 gerado (`relatorio_CAMPINA GRANDE_2026-08-10_2026-08-16.docx`) via tool `getRelatorioSemanal` em conversa real.

### Pendências

- **Extensão futura (não implementar agora)**: integração Telegram para enviar relatório automaticamente ou alertar quando pronto.

## Sprint 5 — O agente: tools no OpenCode + Gemini

Status: **concluído** (validado em conversa real no opencode desktop; escopo Sheets antecipado do planejamento original).

### Feito

- Plugin `.opencode/plugins/operacoes.ts` (auto-descoberto pelo opencode, sem registrar em `opencode.json`):
  - `getDiagnosticoTecnico` → `GET /diagnostico/tecnico/{nome}?periodo_de=&periodo_ate=`.
  - `getStatusUnidade` → `GET /diagnostico/status-unidade/{unidade}?periodo_de=&periodo_ate=`.
  - **Divergências do roadmap corrigidas**: endpoint real tem prefixo `/diagnostico/...` (não `/diagnostico-tecnico/...`) e datas em `YYYY-MM-DD` (não `YYYYMMDD`).
  - Datas opcionais: se o modelo omitir, o plugin calcula a **semana atual local** (segunda–domingo) — default alinhado com a janela de sync. Bug corrigido: `toISOString()` deslocava a data em UTC; agora formata com componentes locais.
  - Token: lê `OPS_API_TOKEN` de `process.env`; se ausente, carrega do `.env` do projeto (o opencode **não** injeta `.env` do projeto no processo dos plugins). Envia `Authorization: Bearer`.
  - `getComparativoUnidades` deixado de fora de propósito — validar as duas primeiras na prática primeiro (decisão do usuário).
- Autenticação da API:
  - `OPS_API_TOKEN` em `app/config.py` (via env) e `.env.example`.
  - `app/security.py`: dependência `exigir_token_ops` (HTTPBearer) — token ausente no servidor → 503; header ausente/inválido → 401. Aplicada no router `/diagnostico/*`.
  - `.env` ganhou `OPS_API_TOKEN` gerado (valor não exibido).
  - `/health` continua aberto.
- Agente `.opencode/agent/operacoes.md` (mode primary, `google/gemini-2.5-pro`): system prompt consultivo — nunca decide, só lê/cruza/explica, não inventa números, recusa pedidos de ação. Legendas de escala salvas no prompt: T-1 (08–12/14–18), T-4 (08–12/13:12–18), T-9 (plantão), T-10 (plantão), DSR, BAN, FOL, FER. `opencode.json` criado com `default_agent: operacoes`.
- Validação:
  - pytest: 31 passed.
  - Auth via TestClient: 401 sem token, 401 token errado, passa da auth com token correto; health 200.
  - Ponta a ponta com uvicorn + Postgres real: `status-unidade CAMPINA GRANDE` (43.36 HE, 24 recorrências) e `diagnostico-tecnico ALVARO...` (9 produtivas) → 200.

### Pendências

- ~~Usuário **reiniciar o opencode** (config nova não é hot-reload) e validar com perguntas em linguagem natural~~ — **concluído 2026-08-16**.
- Se `google/gemini-2.5-pro` não resolver com as credenciais do usuário, ajustar o model no frontmatter do agente.
- Depois de validar as duas tools, adicionar `getComparativoUnidades`.

### Correções da validação (2026-08-16)

Validação real no opencode desktop revelou 2 problemas, ambos corrigidos:

1. **Filtro de unidade por igualdade exata** em `_status_unidade` (`SolicitacaoServico.unidade == unidade`): o banco grava `REG-CAMPINA GRANDE`/`REG-LAGOA SECA`, mas o endpoint recebe o nome puro — retornava `abertas=0` para qualquer unidade. Corrigido para `unidade.ilike(f"%{normalizar_unidade(unidade)}%")`, mesmo padrão da query de recorrência.
2. **Semântica de `abertas` ≠ painel**: o painel-ope mostra "aberto agora" = **estado atual** de todas as OS abertas na unidade, **excluindo** naturezas `RECOLHIMENTO` e `RECOLHIMENTO AGENDADO` (e natureza vazia). O endpoint contava só OS abertas *na semana* (e incluía recolhimentos). Decisão do usuário (validada 2026-08-16): `abertas` = estado atual excluindo recolhimentos; `fechadas_produtivas`/`fechadas_improdutivas`/`canceladas` continuam filtrando pelo período do endpoint.
   - LAGOA SECA: **46** abertas agora (bate com o painel), 142 produtivas/16 improdutivas/1 cancelada na semana.
   - CAMPINA GRANDE: 349 abertas agora, 418 produtivas/54 improdutivas/20 canceladas na semana.

pytest: 31 passed. Backend reiniciado (porta 8100).

### Validação real (2026-08-16)

Conversa real no opencode desktop validou o Sprint 5. Perguntas testadas:
- "Qual a situação de MATHEUS FERNANDES DA SILVA?" → tool `getDiagnosticoTecnico` retornou 6 reaberturas/26 protocolos, alerta de recorrência disparou corretamente.
- "Comparar status das unidades" → tool `getStatusUnidade` retornou dados corretos (LAGOA SECA: 46 abertas, CAMPINA GRANDE: 349 abertas).
- Agente interpretou dados, sugeriu ações (foco em MATHEUS, levantar protocolos reabertos) — modo consultivo funcionando.

### Escopo Sheets antecipado (decisão de negócio, 2026-08-16)

A integração Google Sheets foi antecipada do planejamento original (Sprint 3) para o Sprint 5, por duas razões: (1) o usuário já tinha a service account pronta e (2) a planilha é usada frequentemente pelo operacional — acesso rápido via agente agiliza o fluxo de trabalho.

- Tool `getPlanilha` adicionada ao plugin (lista abas + lê dados).
- `SheetsClient` reescrito para leitura genérica de qualquer aba (não só Inspeção).
- Extensão futura registrada: integração Telegram para alertas automáticos (não implementar agora).

## Sprint 4 — Endpoints de cruzamento

Status: **em andamento** (endpoints e alertas implementados; limites calibrados pelo usuário; aguarda validação manual do diagnóstico contra os painéis).

### Decisão de negócio — calibração dos limites de alerta (2026-08-15)

Validada pelo usuário. **Não resetar para os padrões antigos em sessões futuras:**

| Limite | Antes | Agora | Justificativa de negócio |
|---|---|---|---|
| `LIMITE_REABERTURA` | 3 | **1** | Qualquer reabertura em menos de 30 dias para o **mesmo cliente** já é crítica — é definição de negócio, não limiar estatístico. Para refletir isso, a comparação mudou de `>` para `>=` (1 reabertura já dispara). |
| `LIMITE_HE_SEMANAL` | 8.0 | **8.0** (mantido) | Confirmado como adequado. |
| `META_INSPECAO` | 7.0 | **7.0** (mantido) | Escala 0-10, confirmada. |

Testes atualizados em `tests/test_calcular_alerta.py` (31 passed no total): agora cobrem "1 reabertura já alerta", "2 reaberturas alerta" e "limite exato dispara".

### Feito

- `app/services/cruzamento.py`: cruzamento das 3 fontes (leitura só do Postgres).
  - `normalizar_unidade()`: 'REG-CAMPINA GRANDE' / 'UNIDADE CAMPINA GRANDE' / 'CAMPINA GRANDE | PB' → 'CAMPINA GRANDE' (chave comum das 3 fontes).
  - `buscar_metricas_recorrencia`, `buscar_produtividade` (abertas/fech_prod/fech_improd/canceladas via `_is_aberta` do sync_proxxima), `buscar_banco_horas_tecnico` (rankTecHE do snapshot), `buscar_banco_horas_unidade` (cardsUnidadeHE + infracao), `buscar_ultima_inspecao`.
  - `_calcular_alerta()`: regras puras (reabertura `>=` 1, HE `>` 8.0, pontuação `<` 7.0).
- Endpoints `app/routers/diagnostico.py`:
  - `GET /diagnostico/tecnico/{nome_tecnico}?periodo_de=&periodo_ate=` — diagnóstico completo (recorrência + produtividade + HE/infrações + inspeção + alertas).
  - `GET /diagnostico/status-unidade/{unidade}?periodo_de=&periodo_ate=` — backlog + HE + recorrência agregados.
  - `GET /diagnostico/comparativo-unidades?periodo_de=&periodo_ate=` — Campina Grande vs Lagoa Seca lado a lado.
- Validado com dados reais:
  - ALVARO CORREIA DE SOUSA NETO (ago/2026): 12 protocolos, 3 reaberturas → agora **dispara alerta** (regra `>=` 1).
  - MATHEUS FERNANDES DA SILVA: 12 reaberturas → alerta dispara.
  - status-unidade CG: 723 abertas, 1095 produtivas, 43.36 HE (bate com cardsUnidadeHE); LAGOA SECA: 117 abertas, 11.58 HE, 1 infração.
- Testes: 31 passed (inclui `test_calcular_alerta.py` com a calibração nova).

### Pendências

- **Achado do dashboard — saldo acumulado de banco de horas "Positivo +150:37 / Negativo -41:20" (concluído em 2026-08-15)**: investigado e concluído — **não existe endpoint próprio** para esse saldo. Probes em `/api/saldo`, `/api/saldo-geral`, `/api/banco-horas`, `/api/bh`, `/api/extrato`, `/api/painel`, `/api/home`, `/api/cards` → todos 404. `/api/analises` + `/api/semanatec` são os únicos endpoints de dados confirmados, e as chaves documentadas de `analises` não expõem saldo acumulado. **Conclusão**: o saldo é **derivado no frontend** a partir do payload completo de `/api/analises` (soma de `trabalhado − previsto` por técnico/dia, sobre os 97 técnicos do ciclo). Evidência: cálculo manual no top-10 do `rankTecHE` deu +153:33/-23:20 (próximo, mas não exato — o `rankTecHE` é só o top-10 e não traz o detalhe diário de todos os técnicos). **Pendência de implementação futura**: para reproduzir esse saldo no nosso backend, precisamos ou de um payload que exponha o detalhe completo de todos os técnicos, ou validar a fórmula com o usuário (definição de "saldo", quais dias/unidades, e como o "Ant:" é calculado). Não implementado — decisão registrada conforme regra de não ação autônoma.
- Usuário validar manualmente o diagnóstico de um técnico conhecido contra o que via nos painéis.

## Sprint 3 — Recorrência (Excel + join) e Inspeção (Sheets)

Status: **em andamento** (recorrência completa e validada com arquivo real; SheetsClient pronto, aguardando service account).

### Feito

- `app/etl/recorrencia.py`: ETL do analítico de recorrência.
  - Estrutura real validada em `recorrencia_2026-08_campina-grande.xlsx` (C:\Users\proxx\Downloads): aba `Analitico`, linha 0 = grupos, linha 1 = headers, dados a partir da linha 2. `header=1` com `.strip()` nas colunas.
  - Parsers robustos: `_as_str`, `_as_protocolo` (remove `.0` de float do pandas em `Protocolo`/`Protocolo anterior`), `_as_datetime`, `_as_int`.
  - Join protocolo↔técnico: `_mapa_protocolo_tecnico_em_lotes` (função pura testável, lote de 1000) + `_buscar_mapa_protocolo_tecnico` lendo do Postgres já sincronizado (sem chamar API).
  - Upsert por `protocolo` (chave única) via `db.merge`.
- **Correção de modelagem**: a FK `ocorrencia_recorrencia_protocolo_anterior_fkey` impedia o import — todos os 83 protocolos anteriores estão fora da janela de 30 dias (não estão no arquivo). FK removida do modelo e do banco; `protocolo_anterior` virou Text informativo.
- **Import real**: 463 importadas, 83 recorrentes (bate com o manual), 4 sem técnico (fora do lookback — esperado, critério de pronto ok).
- Endpoints `app/routers/recorrencia.py`:
  - `GET /recorrencia/por-tecnico?tecnico=&periodo_de=&periodo_ate=` — total de protocolos e contagem `é_recorrencia = SIM` no período.
  - `GET /recorrencia/detalhe?tecnico=&periodo_de=&periodo_ate=` — detalhe para conferir com o painel.
  - Validados com dados reais (ex. ALVARO...: 12 protocolos, 3 recorrentes).
- `app/services/sheets_client.py`: `SheetsClient` (gspread + service account via env `SHEETS_SERVICE_ACCOUNT_JSON`/`SHEETS_SPREADSHEET_URL`), `ler_inspecoes()`, `tecnico_valido_roster()`, `_parse_data_sheets()`. Sem credenciais, loga warning e retorna vazio (padrão do Telegram).
- `.env.example` atualizado (vars do Sheets); `requirements.txt` com `pandas`, `openpyxl`, `gspread`.
- Testes: 21 passed (ETL: parsers, estrutura do Excel, loteamento do join).

### Pendências

- Validação manual do usuário: `/recorrencia/por-tecnico` bate com o que ele via no painel de recorrência.
- ~~Criar service account do Google Sheets e preencher `SHEETS_SERVICE_ACCOUNT_JSON`/`SHEETS_SPREADSHEET_URL`~~ — **concluído em 2026-08-16**.
- Usuário vai migrar para planilha online diária (hoje é export manual local) — quando isso acontecer, o ETL passa a ler dessa planilha.

### Integração Google Sheets completa (2026-08-16)

- `SheetsClient` reescrito para leitura genérica: `listar_abas()`, `ler_aba(nome)`, `ler_todas()`. Suporta arquivo (`SHEETS_SERVICE_ACCOUNT_FILE`) ou string JSON (`SHEETS_SERVICE_ACCOUNT_JSON`).
- `credencial.json` corrigido (`client_email` continha URL da planilha em vez do email da service account). Adicionado ao `.gitignore`.
- Service account `agente-ope-sheets@agenteope.iam.gserviceaccount.com` compartilhada na planilha (editor).
- Planilha: **UNIDADE CAMPINA GRANDE _ LAGOA SECA** — 36 abas (COLABORADORES, BASE, BASE 3 MESES, BASE PRODUÇÃO, PRODUÇÃO, PRODUÇÃO MÊS, RESULTADO, ABERTURA, FÉRIAS, ESCALAS mensais, DOUGLAS/JURACI/CARLOS, REGIÕES, FERRAMENTAL, PENDENCIAS, etc.).
- Endpoint `GET /planilha/abas` (lista abas) e `GET /planilha/{aba}?limite=` (lê dados) — protegido por `exigir_token_ops`.
- Tool `getPlanilha` adicionada ao plugin `.opencode/plugins/operacoes.ts` — primeiro chama sem aba (lista), depois com nome da aba (dados).

## Sprint 2 — painel-ope (banco de horas, HE, infrações)

Status: **em andamento** (etapas 1 e 2 feitas; job, endpoints e sync real concluídos; falta validação manual do usuário).

### Feito

- Etapa 1 — `app/services/painel_ope_client.py`: `PainelOpeClient` (httpx síncrono, cookie via `settings.ope_session_cookie`), `_decodificar_payload_jwt` (aceita 2 segmentos `payload.sig` e JWT clássico 3 segmentos, prefere o que tem `exp`), `dias_para_expirar()` (`math.ceil`), `get_analises(de, ate, setor)` e `get_semanatec(setor)`; 401/403 → `AuthenticationError`. Nunca loga/imprime o valor do cookie.
- Etapa 2 — probe real (sem tocar em banco), descobertas apresentadas e validadas com o usuário:
  - Setores válidos: `REG01`, `REG02`, `REG03`, `EXPANSAO`, `PMO`, `REDES`. **Não há código próprio para Lagoa Seca** — REG02 cobre Campina Grande + Lagoa Seca (filtro de unidade é client-side).
  - `analises` aceita `de`/`ate` em `YYYYMMDD` (dashboard) e `YYYY-MM-DD`; aceita mês inteiro (validado `20260701–20260731`); `periodo.modo='semana'` é só rótulo.
  - Decisão do usuário: sincronizar **apenas REG02**.
  - Decisão do usuário: modelo `infracao` ajustado ao payload real — **sem coluna `dias`**; campos reais: `nome`(técnico), `sup`, `unidade`, `data`(=`dataKey`), `detalhe`(motivo), `batidas`, `previsto`, `autorizado`, `justificativa`.
- Job `app/jobs/sync_painel_ope.py`:
  - `sync_painel_ope()`: semana atual (segunda–domingo) para REG02; `get_analises` → upsert em `banco_horas_semanal` (unique setor+semana_de+semana_ate) + `infracoesListaSemana` → `infracao` (dedup por tecnico+data+motivo, sem ID no payload); `get_semanatec` → `roster_tecnico` (upsert por técnico).
  - `start_scheduler`/`stop_scheduler`: APScheduler diário via lifespan (registrado no `main.py` junto ao do Proxxima); só agenda se cookie configurado.
  - Logs apenas com contagens e estado do cookie — nunca o valor.
- Endpoints async `app/routers/banco_horas.py`:
  - `GET /banco-horas/analises?setor=` (e `de`/`ate` opcionais) — lê o snapshot do Postgres e extrai totais do payload. Assinatura alinhada ao critério de pronto do roadmap (`de`/`ate`).
  - `GET /banco-horas/roster?setor=` — lista de técnicos (validador de nomes).
  - `GET /banco-horas/status-cookie` — `{configurado, expira_em_dias}`.
- Alerta Telegram (roadmap Sprint 2, item 4):
  - `app/services/telegram.py`: `avisar_telegram()` (httpx, timeout 15s); sem token/chat configurados, loga warning e segue — nunca derruba o sync.
  - `app/jobs/checar_cookie.py`: `checar_expiracao_cookie()` — alerta quando cookie ausente, inválido (AuthenticationError) ou `dias_para_expirar() <= 1`. Agendado diário junto ao sync.
  - `sync_painel_ope()`: em `AuthenticationError` (401/403), alerta via Telegram e re-levanta (falha controlada, sem contornar autenticação).
- Migração no banco: `infracao` perdeu `dias`; ganhou `unidade`, `sup`, `data` (TEXT/TEXT/DATE).
- Sync real (manual): semana 10–16/08, `he_horas=130.98` (bate com o probe), 4 infrações, roster de 100 técnicos. Endpoints validados via TestClient (200). Testes: 9 passed.

### Pendências

- Validação manual do usuário contra o dashboard (heHoras/infrações/roster de REG02).
- Preencher `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` no `.env` para ativar os alertas (hoje degradam com warning).

## Sprint 0 — Schema fechado + esqueleto FastAPI

Status: **em andamento** (esqueleto e schema prontos; pendências do sprint listadas abaixo).

### Feito

- Schema do Postgres fechado com base nas 4 fontes reais (validado pelo usuário):
  - `solicitacao_servico` (Proxxima GetAll) — `os` normalizado como chave de join
  - `ocorrencia_recorrencia` (Excel "Analítico" + join de técnico)
  - `banco_horas_semanal` + `infracao` (painel-ope `/analises`, snapshot JSONB semanal)
  - `inspecao` (Google Sheets)
  - `roster_tecnico` (validador via `/semanatec`)
- Decisões tomadas com o usuário:
  - **Fora do schema** as tabelas de resumo diário do `aniel-aovivo` (`solicitacao_resumo_diario`, `metrica_recorrencia_diaria`, `metrica_produtividade_diaria`) — viram agregações/views do `solicitacao_servico` no Sprint 4.
  - painel-ope guardado como **snapshot JSONB por semana**; colunas normalizadas (HE, infrações, rankings) só depois de ver um payload real.
- Esqueleto FastAPI criado (sem lógica de negócio):
  - `app/config.py` (pydantic-settings, segredos só via env), `app/db.py` (engine/session/Base/get_db)
  - `app/models/` com os 6 modelos SQLAlchemy (DDL compilado e conferido)
  - `app/routers/` (`/health`), `app/schemas/`, `app/services/`, `app/etl/`, `app/jobs/` (vazios, nomes conforme roadmap)
  - `app/main.py`, `.gitignore`, `.env.example`, `requirements.txt`, `tests/`
- venv `.venv` criada com deps instaladas (FastAPI, SQLAlchemy 2, psycopg3, pydantic-settings); import do app verificado.

### Pendências do Sprint 0 (do roadmap)

- Mapear campos internos de `analises` (HE, infrações, rankings) com um payload real — para definir as colunas normalizadas do painel-ope.
- Confirmar janela de datas aceita por `analises`/`semanatec` (semana vs mês inteiro).
- Criar conta de serviço do Google Sheets (só necessária para Inspeção).
- Testar decodificação do cookie `ope_session` (JWT base64) e montar o alerta de renovação.

### Observações

- AGENTS.md referencia `docs/roadmap.md`, mas o arquivo real é `docs/roadmap-agente-decisao-operacional.md` — tratá-lo como fonte de verdade.
- Commit `eda9a15` = Sprint 0. `/health` foi decouplado do banco (não há Postgres local) — resposta `{"status":"ok"}` validada via uvicorn.

## Sprint 1 — Fundação + Proxxima

Status: **concluído** (sync validado com janela de 30 dias; aguarda validação manual do usuário contra o painel).

### Feito

- `app/services/proxxima_client.py` portado do `proxxima-dashboard` (diff revisado: só imports/config mudaram; lógica de login, token anti-forgery e `GetAll` intacta).
  - Credenciais agora via `settings.proxxima_user`/`proxxima_password` (env), URLs como constantes no módulo, `DEFAULT_LOOKBACK_DAYS = 30`.
- Divergência roadmap×client resolvida com o usuário: payload do `GetAll` **é superconjunto** com as chaves do roadmap (`os`/`tecnico`/`uni`/`nat`/`status`/`abertura`/`venc`/`slaTxt`/`relatos` — o `COLUMNS_DATA` só pede as colunas da tela; o response traz mais).
- **Página de login mudou** (Connect v1.15.2.33): não tem mais `__RequestVerificationToken`. Client adaptado — token opcional (loga warning e segue), mantém suporte caso volte.
- De-para payload→modelo validado com o usuário: `os`=`numero_Obra` split "/", `os_original`=`numero_Obra`, `unidade`=`grupo_Area`, `natureza`=`natureza`, `status`=`status_Execucao`, `tecnico`=`responsavel` (nome maiúsculo), `abertura`/`venc`=`dataHora_Abertura_OS`/`dataHora_Vencimento_OS` (BR→datetime), `sla_status`=`sla`, `relatos`=`observacao`.
- Definição de **OS aberta** aprovada: status não começa com "Fechada" e não é "Cancelado".
- Job `app/jobs/sync_proxxima.py`: upsert em `solicitacao_servico` por `os_original`, em lotes de 1000 (PostgreSQL limita a ~65535 params/statement), APScheduler 30 min via lifespan (não roda em teste manual).
- **Decisão de modelagem**: `numero_Obra` pode ter sub-ordens (`8722521/4`, `8671912/2`); a chave única do upsert passou de `os` para `os_original` (= `numero_Obra` completo), mantendo todas as sub-ordens. `os` (base) virou coluna de join/agrupamento com índice.
- Endpoints async `GET /solicitacoes/resumo?unidade=` e `GET /solicitacoes/por-tecnico?tecnico=` — leitura apenas do Postgres; sem chamada externa no request.
- Sync real (janela 30 dias): 25.769 registros, 0 NULL de técnico, paginação ~52 páginas, tempo ~3 min. Execução manual isolada (scheduler não ativado).

### Pendências

- Validação final do usuário: `por-tecnico`/`resumo` de dados reais batem com o painel (ex.: técnico real + unidade REG-CAMPINA GRANDE).
- Quando validar e ligar o agendamento de produção, subir uvicorn (que ativa o scheduler via lifespan).

### Observações

- Commit `eda9a15` = Sprint 0. Sprint 1 commitado após validação do sync de 30 dias.
- `httpx` e `apscheduler` adicionados ao `requirements.txt`.
