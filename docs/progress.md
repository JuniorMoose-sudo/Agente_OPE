# Progresso — Agente de apoio à decisão operacional

Última atualização: 2026-08-28

## Sprint Hermes — Fase 1: servidor MCP (motor do Hermes Agent)

Status: **concluído** (117 testes passando, transporte MCP validado via stdio).

Decisões do usuário (2026-08-28): Hermes Agent substitui o opencode como interface
principal; rodará na instância AWS Ubuntu (t3.micro) com acesso a todas as APIs;
Telegram primeiro; disparos programados (resumo diário + varredura de alertas);
provider Gemini (chave atual); stack inteira (backend+Postgres+jobs+Hermes) na AWS.

### Feito

- `app/services/mcp_server.py`: servidor MCP `agente-ope` (FastMCP, transporte stdio,
  execução `python -m app.services.mcp_server`).
  - Expõe as mesmas 5 tools do plugin do opencode: `get_diagnostico_tecnico`,
    `get_status_unidade`, `get_tempo_real`, `get_planilha`, `get_relatorio_semanal`.
  - É apenas orquestrador: monta URL/corpo e chama o backend local
    (`OPS_API_URL`, default `http://localhost:8100`) com `Authorization: Bearer
    <OPS_API_TOKEN>` — mantém separação sync/serve; nenhuma API externa chamada daqui.
  - `_semana_atual()` replica o default do plugin (segunda–domingo local).
  - Erros mapeados: 401/403 → `APIError` ("rejeitou o token"), 503 → `APIError`
    ("sem OPS_API_TOKEN"), demais não-2xx propagam `HTTPStatusError`.
  - `get_relatorio_semanal` devolve `download_url` montado a partir de `API_BASE`.
- `tests/test_mcp_server.py`: 19 testes — registro das 5 tools, `call_tool` via
  FastMCP, semana atual (default), mapeamento args→URL (incl. URL-encoding de
  espaços/acentos), header Bearer (com/sem token) e erros 401/403/503/5xx.
- `requirements.txt`: `fastmcp>=3.4` (instalado fastmcp 3.4.7 + mcp 1.29.1).
- `.env.example`: comentário indicando que `OPS_API_URL`/`OPS_API_TOKEN` também
  servem o MCP server.

### Validação

- pytest: **117 passed** (98 anteriores + 19 novos).
- Smoke test real via cliente `mcp` SDK (stdio): as 5 tools aparecem registradas;
  chamada sem backend sobe corretamente `ConnectError` (esperado — backend local
  desligado).

### Pendências (próximas fases)

- Fase 2: instalar Hermes na AWS (Gemini, MCP config, gateway Telegram,
  toolsets restritos).
- Fase 3: skill/persona consultiva + validação com as perguntas do Sprint 5.
- Fase 4: cron (resumo diário 07:30 + varredura de alertas 09:00/17:00 — em
  UTC-3 conforme decisão do usuário).
- Fase 5: docs/transição (default_agent do opencode).

## Sprint Hermes — Fase 0: backend + Postgres na AWS

Status: **concluído** (serviço ativo, health 200, auth 401/200 validada, app
local desligado — AWS é a única instância).

Decisões do usuário (2026-08-28): manter **apenas a AWS** ligada (app local
desligado) e horário de referência **UTC-3**.

### Feito

- Instância `3.147.33.126` (Ubuntu 24.04 LTS, t3.micro, swap 2GB já existente).
  Acesso SSH: `C:\Users\proxx\Downloads\mercado-inteligente-key.pem`.
- Todo o deployment foi feito por SSH (sem tocar código; `.env` enviado por
  scp, valores nunca impressos/logados).
- PostgreSQL 16: role `ops` + banco `agente_ope` (senha gerada no servidor e
  salva só no `.env` local da instância, permissão 600).
- Repo clonado em `/home/ubuntu/agente-ope` (branch main), venv Python 3.12 +
  requirements instalados.
- Serviço systemd `agente-ope.service`: uvicorn em `127.0.0.1:8100`,
  `Restart=always`, WorkingDirectory no repo (o app lê `.env` via pydantic).
- Timezone do SO: `America/Sao_Paulo` (UTC-3) — alinhado ao `TIMEZONE` já usado
  no scheduler do Proxxima; os schedulers diários (painel-ope, TOTVS) herdam o
  TZ do sistema.
- Telegram ativo: bot `AnalistaOPE_bot` validado via `getMe`; token gravado no
  `.env` do servidor.

### Validação

- `GET /health` → 200 (`{"status":"ok","database":"ok"}`), 8 tabelas criadas
  via `create_all` no primeiro boot.
- Auth: 401 sem token / 200 com token Bearer em
  `/diagnostico/status-unidade/CAMPINA GRANDE` (banco vazio, zeros esperados).
- Syncs reais autorizados pelo usuário (rotina idêntica à que rodava local).
  Primeira carga a ~30min do start (interval do Proxxima); painel-ope/TOTVS
  diários.

### Enroscos resolvidos (registro para histórico)

- `.env` Windows com CRLF misto: quebrava a auth (token com `\r` → 401) e o
  dialeto `postgresql` virou `postgesql` (crash `NoSuchModuleError` no boot).
  Normalizado para LF (`tr -d '\r'`) + URL corrigida no servidor.
  **Lições para o próximo deploy**: normalizar `.env` para LF antes de subir e
  validar auth logo após o primeiro boot.
- Schedulers são interval (sem disparo imediato no start) — janela para validar
  antes do primeiro sync real.

### Pendências

- ~~`TELEGRAM_CHAT_ID` ainda não está no `.env` do servidor~~ — **concluído na
  Fase 2** (gravado como `6664094468`, id do próprio usuário).

## Sprint Hermes — Fase 2: Hermes Agent na AWS (Gemini + gateway Telegram + MCP)

Status: **em andamento** (gateway ativo e emparelhado; falta skill/persona —
Fase 3 — e cron — Fase 4).

### Feito

- Modelo configurado hoje: provider `opencode-free` (anônimo, gratuito) +
  `hy3-free` — validado com chat headless (`hermes -z`). Histórico: Gemini free
  esgotou a cota diária (429 "free_tier_requests limit 5" → prepayment
  depleted); `groq` não é provider de LLM neste build (só STT); DeepSeek tem
  chave válida mas o provider do Hermes envia requisição sem header
  Authorization (fallback pendente de correção — chave em `~/.hermes/.env`).
- MCP server `agente-ope` declarado no `~/.hermes/config.yaml` (stdio →
  `/home/ubuntu/agente-ope/.venv/bin/python -m app.services.mcp_server`, env
  `OPS_API_URL=http://127.0.0.1:8100`, `OPS_API_TOKEN=${OPS_API_TOKEN}` via
  `.env` do Hermes). **Fix importante**: `PYTHONPATH=/home/ubuntu/agente-ope`
  necessário no env do MCP — sem ele, o módulo `app` não importa (cwd do Hermes
  ≠ repo) e o servidor MCP morre ("Connection closed").
- Ferramentas do Telegram restritas ao mínimo consultivo: habilitadas apenas
  `file`, `cronjob` e o MCP `agente-ope`; desabilitadas web/browser/terminal/
  vision/image_gen/tts/skills/todo/memory/delegation/code_execution/etc.
- Gateway instalado como serviço do sistema: `hermes gateway install --system
  --run-as-user ubuntu --start-now` (unit `hermes-gateway.service`, ativa no
  boot). Observação: PATH do sudo não inclui `~/.local/bin` — usar caminho
  absoluto com sudo.
- Emparelhamento Telegram: o bot responde ao desconhecido com pairing code;
  `hermes pairing approve telegram <CODIGO>` autorizou o usuário **Junior
  (id 6664094468)** — reconhecido automaticamente na próxima mensagem.
- `TELEGRAM_ALLOWED_USERS=6664094468` no `~/.hermes/.env` e
  `TELEGRAM_CHAT_ID=6664094468` no `.env` do backend (sai o warning de
  allowlist e ativa os alertas do `avisar_telegram`).

### Validação

- Chat headless respondeu em PT-BR via Gemini ✓ e depois via
  opencode-free/hy3-free ✓; `hermes tools list` mostra o MCP `agente-ope` com
  todas as tools e o Telegram só com file/cronjob/MCP ✓; serviços
  `agente-ope.service` e `hermes-gateway.service` ativos ✓.
- 1ª pergunta real via Telegram (28/08 ~10h) gerou chamadas MCP ao vivo no
  backend (tempo-real LAGOA SECA 200, status-unidade CG/LS 200) e o agente
  respondeu com "7 SEM ACESSO abertas hoje em CG, 3 em LS" — o acumulado em
  aberto por natureza não existia no endpoint (motivo da Rota A, abaixo).
- 1º sync do Proxxima rodou (~30 min após boot) e populou o banco:
  **24.165 OS** em `solicitacao_servico`.

### Enroscos resolvidos

- `hermes chat --list-toolsets` não existe nesta versão (só `hermes tools list`).
- Config via `hermes config set` aceita listas YAML (`args`) e variáveis
  `${VAR}` — mantém segredos fora do config.yaml.
- Gateway em "Connecting to Telegram (attempt 1/8)" não é erro: sem TTY ele
  fica aguardando o emparelhamento; a pairing code responde ao primeiro contato.
- 1º restart do gateway falhou por contenção de `gateway.lock` (instância
  antiga ainda liberando) — systemd relançou e estabilizou; sem loop.

### Pendências

- Fase 3: skill/persona consultiva (replicar `.opencode/agent/operacoes.md`) —
  hoje o Hermes responde como agente genérico com as tools MCP.
- Fase 4: cron (resumo diário 07:30 + varredura de alertas 09:00/17:00, UTC-3).
- Validar primeira pergunta real via Telegram (ex.: "como está Campina Grande?").
- Conferir 1º sync do Proxxima populando as tabelas (contagem de
  `solicitacao_servico`).

## Rota A — tempo-real com abertas por natureza (2026-08-28, aprovada pelo usuário)

Status: **implementado + testado**.

Motivo: o bot respondeu à pergunta "quantos protocolos SEM ACESSO estão em
aberto?" com apenas as abertas de hoje (o endpoint `tempo-real` só quebrava por
natureza o que abriu/encerrou hoje). O acumulado em aberto por natureza já
existia na lista `abertas` obtida do GetAll (campo `natureza`), faltava agrupar.

### Feito

- `app/routers/diagnostico.py`: novo campo `abertas_agora_por_natureza` no
  endpoint `GET /diagnostico/tempo-real/{unidade}` (Counter por natureza sobre
  as OS abertas da unidade) + `natureza=None` passa a cair em `"N/A"` (antes
  virava chave `None` — acontece quando a API devolve null).
- `app/services/mcp_server.py`: docstring do tool `get_tempo_real` atualizada
  (o MCP repassa o JSON do endpoint — sem mudança de contrato).
- `tests/test_tempo_real.py`: 5 testes (fake do `ProxximaClient` via
  monkeypatch — sem chamada real à API): filtro por unidade, exclui
  fechadas/canceladas, `None`→N/A, regressão das chaves originais, unidade
  inválida. Suíte: **122 testes passando**.

### Resultado ao vivo (Consulta no Postgres, ~11h, estado do sync 10:30)

- SEM ACESSO em aberto: **CG = 22**, **LS = 7** (mais 159 em outras unidades
  que o GetAll retorna — fora do escopo).

### Pendências (fora desta rota)

- Sheets: `credencial.json` da service account não existe na AWS (o bot viu
  503 em `/planilha/abas`) — copiar arquivo ou usar
  `SHEETS_SERVICE_ACCOUNT_JSON` no `.env`.
- Fase 3/4 (skill persona + cron) — ver seção Fase 2.

## Fase 3 — Persona consultiva no Hermes (2026-08-28)

Status: **implementado e validado** (aguardando validação do usuário no Telegram).

### Feito

- Persona canônica criada em `docs/persona-hermes.md` (fonte única no repo:
  papel puramente consultivo, como responder, tabela de tools com quando usar,
  `get_tempo_real` com `abertas_agora_por_natureza` para "SEM ACESSO em aberto
  agora", legendas de escala T-1/T-4/T-9/T-10/DSR/BAN/FOL/FER, relatórios).
- Copiada para `/home/ubuntu/.hermes/persona-operacoes.md` (4.351 bytes).
- Injetada via `agent.coding_instructions` no `~/.hermes/config.yaml`
  (round-trip yaml via python com backup em `config.yaml.bak-persona`).
  Mecanismo descoberto: `agent/coding_context.py::_coding_instructions` →
  `coding_system_prompt_parts` — só entra no prompt quando `valid_tool_names`
  não é vazio (por isso teste com `--safe-mode` não mostra a persona; o gateway
  Telegram não usa safe-mode e funciona).
- Gateway reiniciado (sessões novas já carregam a persona).

### Validação (headless, sem safe-mode)

- "O que você é? Pode abrir uma OS?" → respondeu como **assistente consultivo
  do OPE**, recusou abrir OS ("só consigo LER dados") e puxou **dado real ao
  vivo**: 17 SEM ACESSO abertas em CG (API Proxxima 11:38), 268 abertas, 162
  SLA vencido, 192 sem técnico — comportamento igual ao do agente opencode.

### Pendências

- Validação do usuário no Telegram (persona + resposta SEM ACESSO).
- Fase 4: cron (resumo diário 07:30 + varredura 09:00/17:00, UTC-3).

## Material de Escala Setembro 2026

Status: **concluído** (material gerado e salvo em Downloads).

### O que foi feito

- Lidas as abas `Escala Campina Grande Setembro` e `Escala Lagoa Seca Setembro` do Google Sheets.
- Análise das mudanças: T-1 (08-12/14-18) → T-4 (08-12/13:12-18), ganho de 48 min/dia.
- Plantão (T-9) nos domingos para cobertura.
- DSR distribuído durante a semana, BAN aos sábados.
- Material gerado: `C:\Users\proxx\Downloads\Escala_Setembro_2026_Apresentacao.docx` (12 páginas, 9 seções).

### Conteúdo do material

1. Por que mudamos a escala (acúmulo de +16.7 OS/dia em CG)
2. Situação atual (Agosto)
3. O que muda em Setembro (T-4, ganho 48 min/dia)
4. Nova escala Campina Grande (28 técnicos, 1 em férias)
5. Nova escala Lagoa Seca (11 técnicos)
6. Como funciona o T-4 (comparativo de turnos)
7. Impacto na produtividade (projeção de ganho)
8. Expectativas e metas
9. Perguntas e Respostas

### Arquivo gerado

- `C:\Users\proxx\Downloads\Escala_Setembro_2026_Apresentacao.docx`

### Notas

- Dados do cabeçalho das escalas parecem inconsistentes (datas de julho/ago em vez de set), mas os dados dos técnicos estão corretos.
- Servidor Aniel instável durante a sessão (timeouts recorrentes).

## TOTVS Analytics — Parser hierárquico corrigido + integração no diagnóstico

## TOTVS Analytics — Parser hierárquico corrigido + integração no diagnóstico

Status: **concluído** (parser corrigido, 98 testes passando, dados integrados no endpoint).

### Bug corrigido: offsets locais no parser GoodData

O parser `_build_row_map` e `_build_col_map` em `totvs_client.py` tratava os `index` dos nós da árvore GoodData como **índices absolutos**, mas eles são **locais** (0-based dentro de cada grupo). Cada grupo tem um campo `first` que dá o offset absoluto.

**Impacto**: sem o offset, todos os 17 grupos mapeavam para as mesmas posições (0-N), causando sobreposição. Resultado: 6729 registros com unidade vazia em vez de 17 unidades mapeadas corretamente.

**Correção**: `result[local_idx + group["first"]]` em vez de `result[local_idx]`.

### Dados sincronizados

- **Pontuação por Dia x Técnico e Unidade** (report 2837323): **6.849 registros** não-zero, **17 unidades**, **492 técnicos**.
- **KPI Reparos** (report 4890627): 3 linhas.
- **Premiação Supervisor** (report 1464793): 1 linha.
- Sync completo via `sync_totvs()` — dados persistidos no Postgres (`metrica_totvs`).

### Integração no diagnóstico e relatório

- `cruzamento.py`: nova função `buscar_pontuacao_totvs(db, tecnico, periodo_de, periodo_ate)` — lê o snapshot mais recente de `metrica_totvs` (report 2837323), parseia o `xtab_data` hierárquico, filtra por técnico + período. Retorna média, total, dias com dados, e últimos 10 dias.
- Schema `PontuacaoTotvsResumo` adicionado em `schemas/diagnostico.py`.
- Endpoint `GET /diagnostico/tecnico/{nome}` agora retorna campo `pontuacao_totvs` com média, total, dias e detalhes.
- `relatorio.py`: nova seção 10 "Pontuação TOTVS por Técnico" no relatório semanal:
  - `_buscar_pontuacao_totvs_por_tecnico()` — lê o snapshot, filtra por unidade normalizada + período, agrega por técnico (média, total, dias, melhor, pior).
  - Tabela com top 20 técnicos ordenados por média.
  - Resumo: média geral da unidade, técnicos acima/abaixo da meta (≥7.0 / <7.0).
  - Fontes atualizadas na seção 11 (Observações) para incluir TOTVS Analytics.
- Validado com FLAVIO NASCIMENTO VIEIRA: média 6.93, 39 dias com dados, 270.43 total.
- Relatório ID 6 gerado com sucesso para CAMPINA GRANDE (11/08-17/08/2026) — seção TOTVS com dados reais.

### Testes

- 98 testes pytest passando (93 existentes + 5 novos para o parser hierárquico).
- `TestParseHierarquico`: offset 2 grupos, 3 grupos, col offset, skip zeros, sem unidade vazia.
- Robustez: parser agora trata `0` numérico além de `"0"` string.

### Arquivos alterados

- `app/services/totvs_client.py`: `_build_row_map`, `_build_col_map` com offset; robustez zero.
- `app/services/cruzamento.py`: `buscar_pontuacao_totvs` + imports.
- `app/services/relatorio.py`: `_buscar_pontuacao_totvs_por_tecnico`, seção 10 no relatório.
- `app/schemas/diagnostico.py`: `PontuacaoTotvsResumo`.
- `app/routers/diagnostico.py`: chamada + resposta.
- `tests/test_totvs_client.py`: 5 novos testes hierárquicos.

## Sprint 7 — Robustez

Status: **concluído** (testes pytest expandidos de 31 para 98; TOTVS integrado).

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
- `tests/test_totvs_client.py` (novos):
  - `TestParseHierarquico` — 5 testes cobrindo offset de grupos (2 e 3 grupos), offset de colunas (2 datas), skip de zeros, e garantia de unidade não vazia.
- pytest: **98 passed** (31 originais + 51 Sprint 7 + 5 TOTVS + 11 extras).

### Observações sobre scheduling

O agendamento (APScheduler) já está implementado nos Sprints 1 e 2:
- `sync_proxxima`: 30 minutos via lifespan (`app/main.py`).
- `sync_painel_ope`: diário via lifespan.
- `checar_cookie`: diário via lifespan.
Todos os three jobs estão ativos quando o uvicorn sobe. Não é necessário implementar scheduling adicional no Sprint 7.

### Pendências

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

## Fase 4 — Cron de resumo e alertas no Hermes (2026-08-28)

Status: **implementado e validado ponta a ponta** (entrega no Telegram confirmada nos logs do gateway; aguarda confirmação visual do usuário).

### Feito

- 3 jobs criados no `hermes cron` (scheduler do gateway, UTC-3):
  - `94a08eebbd48` — **Resumo Diario OPE (07:30)**: `30 7 * * *`, entrega `telegram:6664094468`. Prompt: resumo diário com `get_tempo_real` (2 unidades) + `getStatusUnidade` (semana) — panorama agora (por natureza, destaque SEM ACESSO, SLA vencido, sem técnico), fechadas hoje, HE e recorrências da semana; números primeiro, consultivo, encerra com decisão do coordenador.
  - `d3c002570220` — **Varredura Alertas OPE (09h)**: `0 9 * * *`, `--continuity`. Limites calibrados do Sprint 4: recorrência ≥1 reabertura, HE > 8h, inspeção < 7.0 (planilha via `getPlanilha`; se 503, informa indisponível).
  - `f09fa0260230` — **Varredura Alertas OPE (17h)**: `0 17 * * *`, `--continuity` (mesmo prompt da manhã). Primeiro disparo real: **28/08 às 17:00**.
- **Aprendizados de entrega** (importantes):
  - `deliver=telegram` (sem chat) criado via CLI não resolve alvo → usar **`telegram:6664094468`** explícito (`no delivery target resolved for deliver=telegram`).
  - **NÃO usar `hermes cron run` via ssh** para validar: o processo dono da execução é o CLI e morre quando a sessão ssh fecha → execução vira `unknown` e a entrega se perde (`Reclaimed 1 cron execution(s) whose owner process died`). Runs reais rodam no processo do gateway (dono estável) — exemplos `source=builtin` de 12:06/12:08 completando e entregando (`delivered to telegram:6664094468 via live adapter`).
  - Validação por tick real: editar schedule para `*/2 * * * *`, observar o gateway disparar, e reverter — funcionou.

### Validação ponta a ponta

- Run de teste 12:06: job completou com 2694 chars; log do gateway: `12:07:23 delivered to telegram:6664094468 via live adapter`.
- Run extra 12:08 (tick residual antes do revert) também entregue — usuário deve ter recebido **dois** resumos no Telegram (~12:07 e ~12:09).

### Pendências

- **Renovar cookie do painel Operações ~a cada 4 dias** (expira 2026-09-01 17:05) — job alerta no Telegram se expirar.
- Confirmação visual do usuário (mensagens ~12:07/12:09 no bot).
- Observar o primeiro disparo automático da **varredura das 17:00** de 28/08.
- Inspeção na varredura depende da credencial do Sheets na AWS (pendência conhecida).
- **Decisão de domínio pendente**: atribuir recorrência ao técnico da **OS atual** (feito hoje, validado) ou ao técnico da **OS anterior** (quem causou a reabertura) — questionar o coordenador antes de mudar.

## Correção: rótulo de recorrência no diagnóstico por técnico (2026-08-28)

### Problema relatado

O agente respondeu que ALVARO CORREIA tinha 22 recorrências em agosto e que isso
"concentrava 100% das recorrências de CG num único técnico". O coordenador negou:
há recorrências de várias equipes.

### Investigação (dados reais no Postgres)

- **A atribuição JOIN estava CORRETA**: 33 técnicos distintos têm recorrência em CG
  em ago/2026 (total 195). ALVARO CORREIA DE SOUSA NETO tem **4 recorrências**.
- **Raiz do erro**: o campo JSON `recorrencia_total_protocolos` contava **todas as OS
  do técnico no analítico** (22 — inclui as não-recorrentes), não as recorrências.
  O nome induzia o LLM a ler "22 protocolos com recorrência" e a montar a narrativa.

### Correção aplicada

- Schema `DiagnosticoTecnico`: `recorrencia_total_protocolos` renomeado para
  `recorrencia_os_no_analitico` + novo campo `recorrencia_contexto` (frase explícita:
  quantas OS no analítico e quantas são recorrência).
- Descrição da tool `getDiagnosticoTecnico` no plugin: documenta que para recorrências
  do técnico o campo certo é `recorrencia_reaberturas`.
- 131 testes verdes. Fix commitado junto.

## Ranking de recorrência e quebra por problema (2026-08-28)

Status: **implementado e com testes** (aguarda deploy + validação no bot).

### Contexto

O bot (Hermes) não conseguia responder "5 maiores ofensores de recorrência" nem
"recorrência por natureza": as tools MCP não tinham ranking e o agente não tem
como listar técnicos sozinho. Os dados já estavam no Postgres.

### Feito

- `GET /recorrencia/ranking?unidade&periodo_de&periodo_ate&top=5` — agrega
  `é_recorrencia=SIM` por técnico numa única query: `recorrencias` (a métrica),
  `os_no_analitico` (só contexto, para não repetir o erro de rótulo), `taxa`,
  `total_recorrencias` da unidade e top (1–20). Exclui técnicos sem join.
- `GET /recorrencia/por-problema?unidade&periodo_de&periodo_ate` — contagem de
  recorrências por `problema_fechamento` + `resumo_categorias` em 3 grupos macro
  (`categorizar_problema`: administrativo = CLIENTE DESISTIU/EM MASSIVA,
  rede_externa = ORIGEM REDES/INFRA, default = culpa_do_campo — ajustável).
- Tools MCP novas (`app/services/mcp_server.py`): `get_ranking_recorrencia` e
  `get_recorrencia_por_problema` (o bot do Telegram vê estas). Espelhadas no
  plugin `.opencode/plugins/operacoes.ts`.
- Testes: `tests/test_recorrencia_endpoints.py` (categorização + agregações com
  fake DB) e MCP atualizado (7 tools + URLs). **152 passed**.

### Pendências

- Deploy AWS + curl de validação (esperado: ranking CG/ago com MATHEUS 23
  primeiro e ALVARO 4; por-problema com CONECTOR 48 encabeçando).
- Validação do usuário no bot ("quais os 5 técnicos com mais recorrências em CG
  na semana?"; "recorrências por natureza em CG").

## Rota Painel Operações — recorrência sem planilha (2026-08-28)

Status: **implementado, testado ao vivo e importado na AWS** (aguarda validação
do usuário no Telegram/consultas).

### Contexto

- O painel `operacoes.proxxima.net` (server-rendered) tem a recorrência **por
  protocolo** na página `/painel/recorrencia/analitico?mes=YYYY-MM&unidade=UNIDADE X`,
  que **baixa o mesmo Excel "Analítico" do export manual** (aba `Analitico`, 1.028
  linhas CG em ago/2026 vs 463 do export antigo).
- **Auth = Zoho SSO** (sem usuário/senha de API; página `/login` confirma) →
  acesso programático pelo **cookie `bl_session`** (mesmo padrão do painel-ope).

### Feito

- `OPERACOES_SESSION_COOKIE` no `app.config.Settings` (o valor real só no `.env`
  da AWS; validade até 2026-09-01 17:05).
- `app/services/operacoes_client.py`: `OperacoesClient.fetch_analitico(unidade, mes)`
  → bytes do xlsx; detecta expiração (303/`/login`); valida magic `PK`;
  URL form-urlencoded (`UNIDADE+CAMPINA+GRANDE`).
- `app/jobs/sync_recorrencia_painel.py`: baixa CG+LS do mês corrente, grava em
  temp, reusa **`importar_recorrencia`** (parser sem mudança — 13 colunas
  esperadas presentes no painel), remove temp, **alerta Telegram** se o cookie
  expirar (relança `OperacoesAuthError`, nunca contorna auth). Scheduler diário
  **06:15 UTC-3** (guard: cookie presente; wiring no `main.py`).
- Testes: `test_operacoes_client.py` (6) + `test_sync_recorrencia_painel.py` (3).
  **131 passed** no total. Commit `c095bd0`.

### Validação ao vivo (AWS, 28/08 ~18:58 UTC-3)

```
UNIDADE CAMPINA GRANDE: importadas 1029, sem_tecnico 13, com_recorrencia 195
UNIDADE LAGOA SECA:      importadas 329, sem_tecnico 2, com_recorrencia 36
```

Banco confirmado: CG 1.029 / LS 329 em `ocorrencia_recorrencia`.

### Pendências / observações

- **Renovar cookie ~a cada 4 dias** (expira 2026-09-01 17:05) — alerta do job
  avisa se expirar; renovar é recapturar o `bl_session` no navegador.
- Planilha (Sheets) continua pendente **só para inspeção**.
