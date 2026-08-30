# Progresso â€” Agente de apoio Ã  decisÃ£o operacional

Ãšltima atualizaÃ§Ã£o: 2026-08-28

## Sprint Hermes â€” Fase 1: servidor MCP (motor do Hermes Agent)

Status: **concluÃ­do** (117 testes passando, transporte MCP validado via stdio).

DecisÃµes do usuÃ¡rio (2026-08-28): Hermes Agent substitui o opencode como interface
principal; rodarÃ¡ na instÃ¢ncia AWS Ubuntu (t3.micro) com acesso a todas as APIs;
Telegram primeiro; disparos programados (resumo diÃ¡rio + varredura de alertas);
provider Gemini (chave atual); stack inteira (backend+Postgres+jobs+Hermes) na AWS.

### Feito

- `app/services/mcp_server.py`: servidor MCP `agente-ope` (FastMCP, transporte stdio,
  execuÃ§Ã£o `python -m app.services.mcp_server`).
  - ExpÃµe as mesmas 5 tools do plugin do opencode: `get_diagnostico_tecnico`,
    `get_status_unidade`, `get_tempo_real`, `get_planilha`, `get_relatorio_semanal`.
  - Ã‰ apenas orquestrador: monta URL/corpo e chama o backend local
    (`OPS_API_URL`, default `http://localhost:8100`) com `Authorization: Bearer
    <OPS_API_TOKEN>` â€” mantÃ©m separaÃ§Ã£o sync/serve; nenhuma API externa chamada daqui.
  - `_semana_atual()` replica o default do plugin (segundaâ€“domingo local).
  - Erros mapeados: 401/403 â†’ `APIError` ("rejeitou o token"), 503 â†’ `APIError`
    ("sem OPS_API_TOKEN"), demais nÃ£o-2xx propagam `HTTPStatusError`.
  - `get_relatorio_semanal` devolve `download_url` montado a partir de `API_BASE`.
- `tests/test_mcp_server.py`: 19 testes â€” registro das 5 tools, `call_tool` via
  FastMCP, semana atual (default), mapeamento argsâ†’URL (incl. URL-encoding de
  espaÃ§os/acentos), header Bearer (com/sem token) e erros 401/403/503/5xx.
- `requirements.txt`: `fastmcp>=3.4` (instalado fastmcp 3.4.7 + mcp 1.29.1).
- `.env.example`: comentÃ¡rio indicando que `OPS_API_URL`/`OPS_API_TOKEN` tambÃ©m
  servem o MCP server.

### ValidaÃ§Ã£o

- pytest: **117 passed** (98 anteriores + 19 novos).
- Smoke test real via cliente `mcp` SDK (stdio): as 5 tools aparecem registradas;
  chamada sem backend sobe corretamente `ConnectError` (esperado â€” backend local
  desligado).

### PendÃªncias (prÃ³ximas fases)

- Fase 2: instalar Hermes na AWS (Gemini, MCP config, gateway Telegram,
  toolsets restritos).
- Fase 3: skill/persona consultiva + validaÃ§Ã£o com as perguntas do Sprint 5.
- Fase 4: cron (resumo diÃ¡rio 07:30 + varredura de alertas 09:00/17:00 â€” em
  UTC-3 conforme decisÃ£o do usuÃ¡rio).
- Fase 5: docs/transiÃ§Ã£o (default_agent do opencode).

## Sprint Hermes â€” Fase 0: backend + Postgres na AWS

Status: **concluÃ­do** (serviÃ§o ativo, health 200, auth 401/200 validada, app
local desligado â€” AWS Ã© a Ãºnica instÃ¢ncia).

DecisÃµes do usuÃ¡rio (2026-08-28): manter **apenas a AWS** ligada (app local
desligado) e horÃ¡rio de referÃªncia **UTC-3**.

### Feito

- InstÃ¢ncia `3.147.33.126` (Ubuntu 24.04 LTS, t3.micro, swap 2GB jÃ¡ existente).
  Acesso SSH: `C:\Users\proxx\Downloads\mercado-inteligente-key.pem`.
- Todo o deployment foi feito por SSH (sem tocar cÃ³digo; `.env` enviado por
  scp, valores nunca impressos/logados).
- PostgreSQL 16: role `ops` + banco `agente_ope` (senha gerada no servidor e
  salva sÃ³ no `.env` local da instÃ¢ncia, permissÃ£o 600).
- Repo clonado em `/home/ubuntu/agente-ope` (branch main), venv Python 3.12 +
  requirements instalados.
- ServiÃ§o systemd `agente-ope.service`: uvicorn em `127.0.0.1:8100`,
  `Restart=always`, WorkingDirectory no repo (o app lÃª `.env` via pydantic).
- Timezone do SO: `America/Sao_Paulo` (UTC-3) â€” alinhado ao `TIMEZONE` jÃ¡ usado
  no scheduler do Proxxima; os schedulers diÃ¡rios (painel-ope, TOTVS) herdam o
  TZ do sistema.
- Telegram ativo: bot `AnalistaOPE_bot` validado via `getMe`; token gravado no
  `.env` do servidor.

### ValidaÃ§Ã£o

- `GET /health` â†’ 200 (`{"status":"ok","database":"ok"}`), 8 tabelas criadas
  via `create_all` no primeiro boot.
- Auth: 401 sem token / 200 com token Bearer em
  `/diagnostico/status-unidade/CAMPINA GRANDE` (banco vazio, zeros esperados).
- Syncs reais autorizados pelo usuÃ¡rio (rotina idÃªntica Ã  que rodava local).
  Primeira carga a ~30min do start (interval do Proxxima); painel-ope/TOTVS
  diÃ¡rios.

### Enroscos resolvidos (registro para histÃ³rico)

- `.env` Windows com CRLF misto: quebrava a auth (token com `\r` â†’ 401) e o
  dialeto `postgresql` virou `postgesql` (crash `NoSuchModuleError` no boot).
  Normalizado para LF (`tr -d '\r'`) + URL corrigida no servidor.
  **LiÃ§Ãµes para o prÃ³ximo deploy**: normalizar `.env` para LF antes de subir e
  validar auth logo apÃ³s o primeiro boot.
- Schedulers sÃ£o interval (sem disparo imediato no start) â€” janela para validar
  antes do primeiro sync real.

### PendÃªncias

- ~~`TELEGRAM_CHAT_ID` ainda nÃ£o estÃ¡ no `.env` do servidor~~ â€” **concluÃ­do na
  Fase 2** (gravado como `6664094468`, id do prÃ³prio usuÃ¡rio).

## Sprint Hermes â€” Fase 2: Hermes Agent na AWS (Gemini + gateway Telegram + MCP)

Status: **em andamento** (gateway ativo e emparelhado; falta skill/persona â€”
Fase 3 â€” e cron â€” Fase 4).

### Feito

- Modelo configurado hoje: provider `opencode-free` (anÃ´nimo, gratuito) +
  `hy3-free` â€” validado com chat headless (`hermes -z`). HistÃ³rico: Gemini free
  esgotou a cota diÃ¡ria (429 "free_tier_requests limit 5" â†’ prepayment
  depleted); `groq` nÃ£o Ã© provider de LLM neste build (sÃ³ STT); DeepSeek tem
  chave vÃ¡lida mas o provider do Hermes envia requisiÃ§Ã£o sem header
  Authorization (fallback pendente de correÃ§Ã£o â€” chave em `~/.hermes/.env`).
- MCP server `agente-ope` declarado no `~/.hermes/config.yaml` (stdio â†’
  `/home/ubuntu/agente-ope/.venv/bin/python -m app.services.mcp_server`, env
  `OPS_API_URL=http://127.0.0.1:8100`, `OPS_API_TOKEN=${OPS_API_TOKEN}` via
  `.env` do Hermes). **Fix importante**: `PYTHONPATH=/home/ubuntu/agente-ope`
  necessÃ¡rio no env do MCP â€” sem ele, o mÃ³dulo `app` nÃ£o importa (cwd do Hermes
  â‰  repo) e o servidor MCP morre ("Connection closed").
- Ferramentas do Telegram restritas ao mÃ­nimo consultivo: habilitadas apenas
  `file`, `cronjob` e o MCP `agente-ope`; desabilitadas web/browser/terminal/
  vision/image_gen/tts/skills/todo/memory/delegation/code_execution/etc.
- Gateway instalado como serviÃ§o do sistema: `hermes gateway install --system
  --run-as-user ubuntu --start-now` (unit `hermes-gateway.service`, ativa no
  boot). ObservaÃ§Ã£o: PATH do sudo nÃ£o inclui `~/.local/bin` â€” usar caminho
  absoluto com sudo.
- Emparelhamento Telegram: o bot responde ao desconhecido com pairing code;
  `hermes pairing approve telegram <CODIGO>` autorizou o usuÃ¡rio **Junior
  (id 6664094468)** â€” reconhecido automaticamente na prÃ³xima mensagem.
- `TELEGRAM_ALLOWED_USERS=6664094468` no `~/.hermes/.env` e
  `TELEGRAM_CHAT_ID=6664094468` no `.env` do backend (sai o warning de
  allowlist e ativa os alertas do `avisar_telegram`).

### ValidaÃ§Ã£o

- Chat headless respondeu em PT-BR via Gemini âœ“ e depois via
  opencode-free/hy3-free âœ“; `hermes tools list` mostra o MCP `agente-ope` com
  todas as tools e o Telegram sÃ³ com file/cronjob/MCP âœ“; serviÃ§os
  `agente-ope.service` e `hermes-gateway.service` ativos âœ“.
- 1Âª pergunta real via Telegram (28/08 ~10h) gerou chamadas MCP ao vivo no
  backend (tempo-real LAGOA SECA 200, status-unidade CG/LS 200) e o agente
  respondeu com "7 SEM ACESSO abertas hoje em CG, 3 em LS" â€” o acumulado em
  aberto por natureza nÃ£o existia no endpoint (motivo da Rota A, abaixo).
- 1Âº sync do Proxxima rodou (~30 min apÃ³s boot) e populou o banco:
  **24.165 OS** em `solicitacao_servico`.

### Enroscos resolvidos

- `hermes chat --list-toolsets` nÃ£o existe nesta versÃ£o (sÃ³ `hermes tools list`).
- Config via `hermes config set` aceita listas YAML (`args`) e variÃ¡veis
  `${VAR}` â€” mantÃ©m segredos fora do config.yaml.
- Gateway em "Connecting to Telegram (attempt 1/8)" nÃ£o Ã© erro: sem TTY ele
  fica aguardando o emparelhamento; a pairing code responde ao primeiro contato.
- 1Âº restart do gateway falhou por contenÃ§Ã£o de `gateway.lock` (instÃ¢ncia
  antiga ainda liberando) â€” systemd relanÃ§ou e estabilizou; sem loop.

### PendÃªncias

- Fase 3: skill/persona consultiva (replicar `.opencode/agent/operacoes.md`) â€”
  hoje o Hermes responde como agente genÃ©rico com as tools MCP.
- Fase 4: cron (resumo diÃ¡rio 07:30 + varredura de alertas 09:00/17:00, UTC-3).
- Validar primeira pergunta real via Telegram (ex.: "como estÃ¡ Campina Grande?").
- Conferir 1Âº sync do Proxxima populando as tabelas (contagem de
  `solicitacao_servico`).

## Rota A â€” tempo-real com abertas por natureza (2026-08-28, aprovada pelo usuÃ¡rio)

Status: **implementado + testado**.

Motivo: o bot respondeu Ã  pergunta "quantos protocolos SEM ACESSO estÃ£o em
aberto?" com apenas as abertas de hoje (o endpoint `tempo-real` sÃ³ quebrava por
natureza o que abriu/encerrou hoje). O acumulado em aberto por natureza jÃ¡
existia na lista `abertas` obtida do GetAll (campo `natureza`), faltava agrupar.

### Feito

- `app/routers/diagnostico.py`: novo campo `abertas_agora_por_natureza` no
  endpoint `GET /diagnostico/tempo-real/{unidade}` (Counter por natureza sobre
  as OS abertas da unidade) + `natureza=None` passa a cair em `"N/A"` (antes
  virava chave `None` â€” acontece quando a API devolve null).
- `app/services/mcp_server.py`: docstring do tool `get_tempo_real` atualizada
  (o MCP repassa o JSON do endpoint â€” sem mudanÃ§a de contrato).
- `tests/test_tempo_real.py`: 5 testes (fake do `ProxximaClient` via
  monkeypatch â€” sem chamada real Ã  API): filtro por unidade, exclui
  fechadas/canceladas, `None`â†’N/A, regressÃ£o das chaves originais, unidade
  invÃ¡lida. SuÃ­te: **122 testes passando**.

### Resultado ao vivo (Consulta no Postgres, ~11h, estado do sync 10:30)

- SEM ACESSO em aberto: **CG = 22**, **LS = 7** (mais 159 em outras unidades
  que o GetAll retorna â€” fora do escopo).

### PendÃªncias (fora desta rota)

- Sheets: `credencial.json` da service account nÃ£o existe na AWS (o bot viu
  503 em `/planilha/abas`) â€” copiar arquivo ou usar
  `SHEETS_SERVICE_ACCOUNT_JSON` no `.env`.
- Fase 3/4 (skill persona + cron) â€” ver seÃ§Ã£o Fase 2.

## Fase 3 â€” Persona consultiva no Hermes (2026-08-28)

Status: **implementado e validado** (aguardando validaÃ§Ã£o do usuÃ¡rio no Telegram).

### Feito

- Persona canÃ´nica criada em `docs/persona-hermes.md` (fonte Ãºnica no repo:
  papel puramente consultivo, como responder, tabela de tools com quando usar,
  `get_tempo_real` com `abertas_agora_por_natureza` para "SEM ACESSO em aberto
  agora", legendas de escala T-1/T-4/T-9/T-10/DSR/BAN/FOL/FER, relatÃ³rios).
- Copiada para `/home/ubuntu/.hermes/persona-operacoes.md` (4.351 bytes).
- Injetada via `agent.coding_instructions` no `~/.hermes/config.yaml`
  (round-trip yaml via python com backup em `config.yaml.bak-persona`).
  Mecanismo descoberto: `agent/coding_context.py::_coding_instructions` â†’
  `coding_system_prompt_parts` â€” sÃ³ entra no prompt quando `valid_tool_names`
  nÃ£o Ã© vazio (por isso teste com `--safe-mode` nÃ£o mostra a persona; o gateway
  Telegram nÃ£o usa safe-mode e funciona).
- Gateway reiniciado (sessÃµes novas jÃ¡ carregam a persona).

### ValidaÃ§Ã£o (headless, sem safe-mode)

- "O que vocÃª Ã©? Pode abrir uma OS?" â†’ respondeu como **assistente consultivo
  do OPE**, recusou abrir OS ("sÃ³ consigo LER dados") e puxou **dado real ao
  vivo**: 17 SEM ACESSO abertas em CG (API Proxxima 11:38), 268 abertas, 162
  SLA vencido, 192 sem tÃ©cnico â€” comportamento igual ao do agente opencode.

### PendÃªncias

- ValidaÃ§Ã£o do usuÃ¡rio no Telegram (persona + resposta SEM ACESSO).
- Fase 4: cron (resumo diÃ¡rio 07:30 + varredura 09:00/17:00, UTC-3).

## Material de Escala Setembro 2026

Status: **concluÃ­do** (material gerado e salvo em Downloads).

### O que foi feito

- Lidas as abas `Escala Campina Grande Setembro` e `Escala Lagoa Seca Setembro` do Google Sheets.
- AnÃ¡lise das mudanÃ§as: T-1 (08-12/14-18) â†’ T-4 (08-12/13:12-18), ganho de 48 min/dia.
- PlantÃ£o (T-9) nos domingos para cobertura.
- DSR distribuÃ­do durante a semana, BAN aos sÃ¡bados.
- Material gerado: `C:\Users\proxx\Downloads\Escala_Setembro_2026_Apresentacao.docx` (12 pÃ¡ginas, 9 seÃ§Ãµes).

### ConteÃºdo do material

1. Por que mudamos a escala (acÃºmulo de +16.7 OS/dia em CG)
2. SituaÃ§Ã£o atual (Agosto)
3. O que muda em Setembro (T-4, ganho 48 min/dia)
4. Nova escala Campina Grande (28 tÃ©cnicos, 1 em fÃ©rias)
5. Nova escala Lagoa Seca (11 tÃ©cnicos)
6. Como funciona o T-4 (comparativo de turnos)
7. Impacto na produtividade (projeÃ§Ã£o de ganho)
8. Expectativas e metas
9. Perguntas e Respostas

### Arquivo gerado

- `C:\Users\proxx\Downloads\Escala_Setembro_2026_Apresentacao.docx`

### Notas

- Dados do cabeÃ§alho das escalas parecem inconsistentes (datas de julho/ago em vez de set), mas os dados dos tÃ©cnicos estÃ£o corretos.
- Servidor Aniel instÃ¡vel durante a sessÃ£o (timeouts recorrentes).

## TOTVS Analytics â€” Parser hierÃ¡rquico corrigido + integraÃ§Ã£o no diagnÃ³stico

## TOTVS Analytics â€” Parser hierÃ¡rquico corrigido + integraÃ§Ã£o no diagnÃ³stico

Status: **concluÃ­do** (parser corrigido, 98 testes passando, dados integrados no endpoint).

### Bug corrigido: offsets locais no parser GoodData

O parser `_build_row_map` e `_build_col_map` em `totvs_client.py` tratava os `index` dos nÃ³s da Ã¡rvore GoodData como **Ã­ndices absolutos**, mas eles sÃ£o **locais** (0-based dentro de cada grupo). Cada grupo tem um campo `first` que dÃ¡ o offset absoluto.

**Impacto**: sem o offset, todos os 17 grupos mapeavam para as mesmas posiÃ§Ãµes (0-N), causando sobreposiÃ§Ã£o. Resultado: 6729 registros com unidade vazia em vez de 17 unidades mapeadas corretamente.

**CorreÃ§Ã£o**: `result[local_idx + group["first"]]` em vez de `result[local_idx]`.

### Dados sincronizados

- **PontuaÃ§Ã£o por Dia x TÃ©cnico e Unidade** (report 2837323): **6.849 registros** nÃ£o-zero, **17 unidades**, **492 tÃ©cnicos**.
- **KPI Reparos** (report 4890627): 3 linhas.
- **PremiaÃ§Ã£o Supervisor** (report 1464793): 1 linha.
- Sync completo via `sync_totvs()` â€” dados persistidos no Postgres (`metrica_totvs`).

### IntegraÃ§Ã£o no diagnÃ³stico e relatÃ³rio

- `cruzamento.py`: nova funÃ§Ã£o `buscar_pontuacao_totvs(db, tecnico, periodo_de, periodo_ate)` â€” lÃª o snapshot mais recente de `metrica_totvs` (report 2837323), parseia o `xtab_data` hierÃ¡rquico, filtra por tÃ©cnico + perÃ­odo. Retorna mÃ©dia, total, dias com dados, e Ãºltimos 10 dias.
- Schema `PontuacaoTotvsResumo` adicionado em `schemas/diagnostico.py`.
- Endpoint `GET /diagnostico/tecnico/{nome}` agora retorna campo `pontuacao_totvs` com mÃ©dia, total, dias e detalhes.
- `relatorio.py`: nova seÃ§Ã£o 10 "PontuaÃ§Ã£o TOTVS por TÃ©cnico" no relatÃ³rio semanal:
  - `_buscar_pontuacao_totvs_por_tecnico()` â€” lÃª o snapshot, filtra por unidade normalizada + perÃ­odo, agrega por tÃ©cnico (mÃ©dia, total, dias, melhor, pior).
  - Tabela com top 20 tÃ©cnicos ordenados por mÃ©dia.
  - Resumo: mÃ©dia geral da unidade, tÃ©cnicos acima/abaixo da meta (â‰¥7.0 / <7.0).
  - Fontes atualizadas na seÃ§Ã£o 11 (ObservaÃ§Ãµes) para incluir TOTVS Analytics.
- Validado com FLAVIO NASCIMENTO VIEIRA: mÃ©dia 6.93, 39 dias com dados, 270.43 total.
- RelatÃ³rio ID 6 gerado com sucesso para CAMPINA GRANDE (11/08-17/08/2026) â€” seÃ§Ã£o TOTVS com dados reais.

### Testes

- 98 testes pytest passando (93 existentes + 5 novos para o parser hierÃ¡rquico).
- `TestParseHierarquico`: offset 2 grupos, 3 grupos, col offset, skip zeros, sem unidade vazia.
- Robustez: parser agora trata `0` numÃ©rico alÃ©m de `"0"` string.

### Arquivos alterados

- `app/services/totvs_client.py`: `_build_row_map`, `_build_col_map` com offset; robustez zero.
- `app/services/cruzamento.py`: `buscar_pontuacao_totvs` + imports.
- `app/services/relatorio.py`: `_buscar_pontuacao_totvs_por_tecnico`, seÃ§Ã£o 10 no relatÃ³rio.
- `app/schemas/diagnostico.py`: `PontuacaoTotvsResumo`.
- `app/routers/diagnostico.py`: chamada + resposta.
- `tests/test_totvs_client.py`: 5 novos testes hierÃ¡rquicos.

## Sprint 7 â€” Robustez

Status: **concluÃ­do** (testes pytest expandidos de 31 para 98; TOTVS integrado).

### Feito

- `tests/test_cruzamento.py` (novos):
  - `TestNormalizarUnidade` â€” 10 testes cobrindo prefixo `REG-`, `UNIDADE `, sufixo `| PB`, case insensitivity, None/vazio, espaÃ§os extras.
  - `TestIsAberta` â€” 11 testes cobrindo todos os status reais (Aberta, Fechada Produtiva/Improdutiva, Cancelado, None, vazio).
  - `TestDeltaStr` â€” 4 testes: igual, aumento, queda, zeroâ†’algo.
  - `TestDeltaPct` â€” 5 testes: igual, +50%, -50%, anterior zero com algo, ambos zero.
- `tests/test_relatorio.py` (novos):
  - `TestAddTitulo`, `TestAddSubsecao`, `TestAddParagrafo`, `TestAddTabela`, `TestEnsureDir` â€” helpers de formataÃ§Ã£o.
  - `TestLogicaCalculo` â€” lÃ³gica de cÃ¡lculo de taxa produtividade, concentraÃ§Ã£o top 3, e deltas de tendÃªncia.
  - `TestIsAbertaRelatorio` â€” `_is_aberta` do mÃ³dulo relatorio (diferente do sync_proxxima).
  - `TestConstantesAlerta` â€” constantes LIMITE_REABERTURA=1, LIMITE_HE_SEMANAL=8.0, META_INSPECAO=7.0.
- `tests/test_totvs_client.py` (novos):
  - `TestParseHierarquico` â€” 5 testes cobrindo offset de grupos (2 e 3 grupos), offset de colunas (2 datas), skip de zeros, e garantia de unidade nÃ£o vazia.
- pytest: **98 passed** (31 originais + 51 Sprint 7 + 5 TOTVS + 11 extras).

### ObservaÃ§Ãµes sobre scheduling

O agendamento (APScheduler) jÃ¡ estÃ¡ implementado nos Sprints 1 e 2:
- `sync_proxxima`: 30 minutos via lifespan (`app/main.py`).
- `sync_painel_ope`: diÃ¡rio via lifespan.
- `checar_cookie`: diÃ¡rio via lifespan.
Todos os three jobs estÃ£o ativos quando o uvicorn sobe. NÃ£o Ã© necessÃ¡rio implementar scheduling adicional no Sprint 7.

### PendÃªncias

- **Testes com DB real (SQLite em memÃ³ria)** â€” adicionar fixtures SQLAlchemy para testar queries de `cruzamento.py` e `relatorio.py` contra banco de teste.

## Sprint 6 â€” RelatÃ³rios automÃ¡ticos

Status: **concluÃ­do** (relatÃ³rio rico 10 seÃ§Ãµes gerado com sucesso, commit `184bb57`).

### Feito

- `app/models/relatorio.py`: modelo `Relatorio` (id, titulo, unidade, periodo_de, periodo_ate, nome_arquivo, caminho, criado_em). Tabela criada automaticamente via `Base.metadata.create_all` no lifespan.
- `app/services/relatorio.py`: `gerar_relatorio_semanal()` â€” relatÃ³rio rico 10 seÃ§Ãµes com python-docx:
  1. **Resumo Executivo** com KPIs (backlog, fechadas, HE, infraÃ§Ãµes, recorrÃªncias) + variaÃ§Ã£o vs perÃ­odo anterior.
  2. **AnÃ¡lise de TendÃªncias** â€” insights automÃ¡ticos (backlog cresceu? produtividade caiu? HE acima do esperado?).
  3. **Produtividade por TÃ©cnico** â€” abertas, produtivas, improdutivas, canceladas, total, taxa de produtividade; destaque melhor/pior.
  4. **RecorrÃªncia por TÃ©cnico** â€” protocolos, reaberturas, taxa, concentraÃ§Ã£o top 3.
  5. **Horas Extras por TÃ©cnico** â€” ranking com totais.
  6. **DistribuiÃ§Ã£o por Natureza** â€” com percentuais.
  7. **DistribuiÃ§Ã£o por Dia da Semana** â€” padrÃµes temporais (dia alto/baixo).
  8. **Risco Combinado** â€” tÃ©cnicos com HE **e** recorrÃªncia simultaneamente (cruzamento de fontes).
  9. **Protocolos com RecorrÃªncia** â€” detalhe por protocolo: tÃ©cnico, problema de fechamento, dias entre OS.
  10. **ObservaÃ§Ãµes e Fontes** â€” timestamp de geraÃ§Ã£o.
  - Compara automaticamente com perÃ­odo anterior (mesma duraÃ§Ã£o, janela deslizante).
  - Helpers: `_delta_str`, `_delta_pct`, `_addSubsecao`, `_addParagrafos`, `_is_aberta`.
  - Queries DB: `_buscar_produtividade_por_tecnico`, `_buscar_naturezas`, `_buscar_distribuicao_dia_semana`, `_buscar_top_protocolos_recorrentes`, `_buscar_tecnicos_com_he_e_recorrencia`.
- `app/routers/relatorio.py`:
  - `POST /relatorios` â€” gera relatÃ³rio (body: `{unidade, periodo_de, periodo_ate}`). Retorna metadados + ID.
  - `GET /relatorios/{id}` â€” metadados do relatÃ³rio.
  - `GET /relatorios/{id}/download` â€” download do `.docx` via `FileResponse` (sem auth â€” viabiliza download direto pelo navegador).
- Plugin `.opencode/plugins/operacoes.ts`: tool `getRelatorioSemanal` â€” chama `POST /relatorios`, retorna ID + `download_url`.
- Agent `.opencode/agent/operacoes.md`: seÃ§Ã£o "RelatÃ³rios" adicionada ao prompt.
- `app/main.py`: router `relatorio` registrado; `Base.metadata.create_all(engine)` no lifespan.
- `app/config.py`: nova opÃ§Ã£o `dir_relatorios` (padrÃ£o `relatorios`).
- `.env.example`: `DIR_RELATORIOS=relatorios` documentado.
- `.gitignore`: `relatorios/` adicionado.
- `requirements.txt`: `python-docx>=1.1` adicionado.
- pytest: 82 passed (31 existentes + 51 novos em Sprint 7).
- **Validado com sucesso**: relatÃ³rio ID 3 gerado (`relatorio_CAMPINA GRANDE_2026-08-10_2026-08-16.docx`) via tool `getRelatorioSemanal` em conversa real.

### PendÃªncias

- **ExtensÃ£o futura (nÃ£o implementar agora)**: integraÃ§Ã£o Telegram para enviar relatÃ³rio automaticamente ou alertar quando pronto.

## Sprint 5 â€” O agente: tools no OpenCode + Gemini

Status: **concluÃ­do** (validado em conversa real no opencode desktop; escopo Sheets antecipado do planejamento original).

### Feito

- Plugin `.opencode/plugins/operacoes.ts` (auto-descoberto pelo opencode, sem registrar em `opencode.json`):
  - `getDiagnosticoTecnico` â†’ `GET /diagnostico/tecnico/{nome}?periodo_de=&periodo_ate=`.
  - `getStatusUnidade` â†’ `GET /diagnostico/status-unidade/{unidade}?periodo_de=&periodo_ate=`.
  - **DivergÃªncias do roadmap corrigidas**: endpoint real tem prefixo `/diagnostico/...` (nÃ£o `/diagnostico-tecnico/...`) e datas em `YYYY-MM-DD` (nÃ£o `YYYYMMDD`).
  - Datas opcionais: se o modelo omitir, o plugin calcula a **semana atual local** (segundaâ€“domingo) â€” default alinhado com a janela de sync. Bug corrigido: `toISOString()` deslocava a data em UTC; agora formata com componentes locais.
  - Token: lÃª `OPS_API_TOKEN` de `process.env`; se ausente, carrega do `.env` do projeto (o opencode **nÃ£o** injeta `.env` do projeto no processo dos plugins). Envia `Authorization: Bearer`.
  - `getComparativoUnidades` deixado de fora de propÃ³sito â€” validar as duas primeiras na prÃ¡tica primeiro (decisÃ£o do usuÃ¡rio).
- AutenticaÃ§Ã£o da API:
  - `OPS_API_TOKEN` em `app/config.py` (via env) e `.env.example`.
  - `app/security.py`: dependÃªncia `exigir_token_ops` (HTTPBearer) â€” token ausente no servidor â†’ 503; header ausente/invÃ¡lido â†’ 401. Aplicada no router `/diagnostico/*`.
  - `.env` ganhou `OPS_API_TOKEN` gerado (valor nÃ£o exibido).
  - `/health` continua aberto.
- Agente `.opencode/agent/operacoes.md` (mode primary, `google/gemini-2.5-pro`): system prompt consultivo â€” nunca decide, sÃ³ lÃª/cruza/explica, nÃ£o inventa nÃºmeros, recusa pedidos de aÃ§Ã£o. Legendas de escala salvas no prompt: T-1 (08â€“12/14â€“18), T-4 (08â€“12/13:12â€“18), T-9 (plantÃ£o), T-10 (plantÃ£o), DSR, BAN, FOL, FER. `opencode.json` criado com `default_agent: operacoes`.
- ValidaÃ§Ã£o:
  - pytest: 31 passed.
  - Auth via TestClient: 401 sem token, 401 token errado, passa da auth com token correto; health 200.
  - Ponta a ponta com uvicorn + Postgres real: `status-unidade CAMPINA GRANDE` (43.36 HE, 24 recorrÃªncias) e `diagnostico-tecnico ALVARO...` (9 produtivas) â†’ 200.

### PendÃªncias

- ~~UsuÃ¡rio **reiniciar o opencode** (config nova nÃ£o Ã© hot-reload) e validar com perguntas em linguagem natural~~ â€” **concluÃ­do 2026-08-16**.
- Se `google/gemini-2.5-pro` nÃ£o resolver com as credenciais do usuÃ¡rio, ajustar o model no frontmatter do agente.
- Depois de validar as duas tools, adicionar `getComparativoUnidades`.

### CorreÃ§Ãµes da validaÃ§Ã£o (2026-08-16)

ValidaÃ§Ã£o real no opencode desktop revelou 2 problemas, ambos corrigidos:

1. **Filtro de unidade por igualdade exata** em `_status_unidade` (`SolicitacaoServico.unidade == unidade`): o banco grava `REG-CAMPINA GRANDE`/`REG-LAGOA SECA`, mas o endpoint recebe o nome puro â€” retornava `abertas=0` para qualquer unidade. Corrigido para `unidade.ilike(f"%{normalizar_unidade(unidade)}%")`, mesmo padrÃ£o da query de recorrÃªncia.
2. **SemÃ¢ntica de `abertas` â‰  painel**: o painel-ope mostra "aberto agora" = **estado atual** de todas as OS abertas na unidade, **excluindo** naturezas `RECOLHIMENTO` e `RECOLHIMENTO AGENDADO` (e natureza vazia). O endpoint contava sÃ³ OS abertas *na semana* (e incluÃ­a recolhimentos). DecisÃ£o do usuÃ¡rio (validada 2026-08-16): `abertas` = estado atual excluindo recolhimentos; `fechadas_produtivas`/`fechadas_improdutivas`/`canceladas` continuam filtrando pelo perÃ­odo do endpoint.
   - LAGOA SECA: **46** abertas agora (bate com o painel), 142 produtivas/16 improdutivas/1 cancelada na semana.
   - CAMPINA GRANDE: 349 abertas agora, 418 produtivas/54 improdutivas/20 canceladas na semana.

pytest: 31 passed. Backend reiniciado (porta 8100).

### ValidaÃ§Ã£o real (2026-08-16)

Conversa real no opencode desktop validou o Sprint 5. Perguntas testadas:
- "Qual a situaÃ§Ã£o de MATHEUS FERNANDES DA SILVA?" â†’ tool `getDiagnosticoTecnico` retornou 6 reaberturas/26 protocolos, alerta de recorrÃªncia disparou corretamente.
- "Comparar status das unidades" â†’ tool `getStatusUnidade` retornou dados corretos (LAGOA SECA: 46 abertas, CAMPINA GRANDE: 349 abertas).
- Agente interpretou dados, sugeriu aÃ§Ãµes (foco em MATHEUS, levantar protocolos reabertos) â€” modo consultivo funcionando.

### Escopo Sheets antecipado (decisÃ£o de negÃ³cio, 2026-08-16)

A integraÃ§Ã£o Google Sheets foi antecipada do planejamento original (Sprint 3) para o Sprint 5, por duas razÃµes: (1) o usuÃ¡rio jÃ¡ tinha a service account pronta e (2) a planilha Ã© usada frequentemente pelo operacional â€” acesso rÃ¡pido via agente agiliza o fluxo de trabalho.

- Tool `getPlanilha` adicionada ao plugin (lista abas + lÃª dados).
- `SheetsClient` reescrito para leitura genÃ©rica de qualquer aba (nÃ£o sÃ³ InspeÃ§Ã£o).
- ExtensÃ£o futura registrada: integraÃ§Ã£o Telegram para alertas automÃ¡ticos (nÃ£o implementar agora).

## Sprint 4 â€” Endpoints de cruzamento

Status: **em andamento** (endpoints e alertas implementados; limites calibrados pelo usuÃ¡rio; aguarda validaÃ§Ã£o manual do diagnÃ³stico contra os painÃ©is).

### DecisÃ£o de negÃ³cio â€” calibraÃ§Ã£o dos limites de alerta (2026-08-15)

Validada pelo usuÃ¡rio. **NÃ£o resetar para os padrÃµes antigos em sessÃµes futuras:**

| Limite | Antes | Agora | Justificativa de negÃ³cio |
|---|---|---|---|
| `LIMITE_REABERTURA` | 3 | **1** | Qualquer reabertura em menos de 30 dias para o **mesmo cliente** jÃ¡ Ã© crÃ­tica â€” Ã© definiÃ§Ã£o de negÃ³cio, nÃ£o limiar estatÃ­stico. Para refletir isso, a comparaÃ§Ã£o mudou de `>` para `>=` (1 reabertura jÃ¡ dispara). |
| `LIMITE_HE_SEMANAL` | 8.0 | **8.0** (mantido) | Confirmado como adequado. |
| `META_INSPECAO` | 7.0 | **7.0** (mantido) | Escala 0-10, confirmada. |

Testes atualizados em `tests/test_calcular_alerta.py` (31 passed no total): agora cobrem "1 reabertura jÃ¡ alerta", "2 reaberturas alerta" e "limite exato dispara".

### Feito

- `app/services/cruzamento.py`: cruzamento das 3 fontes (leitura sÃ³ do Postgres).
  - `normalizar_unidade()`: 'REG-CAMPINA GRANDE' / 'UNIDADE CAMPINA GRANDE' / 'CAMPINA GRANDE | PB' â†’ 'CAMPINA GRANDE' (chave comum das 3 fontes).
  - `buscar_metricas_recorrencia`, `buscar_produtividade` (abertas/fech_prod/fech_improd/canceladas via `_is_aberta` do sync_proxxima), `buscar_banco_horas_tecnico` (rankTecHE do snapshot), `buscar_banco_horas_unidade` (cardsUnidadeHE + infracao), `buscar_ultima_inspecao`.
  - `_calcular_alerta()`: regras puras (reabertura `>=` 1, HE `>` 8.0, pontuaÃ§Ã£o `<` 7.0).
- Endpoints `app/routers/diagnostico.py`:
  - `GET /diagnostico/tecnico/{nome_tecnico}?periodo_de=&periodo_ate=` â€” diagnÃ³stico completo (recorrÃªncia + produtividade + HE/infraÃ§Ãµes + inspeÃ§Ã£o + alertas).
  - `GET /diagnostico/status-unidade/{unidade}?periodo_de=&periodo_ate=` â€” backlog + HE + recorrÃªncia agregados.
  - `GET /diagnostico/comparativo-unidades?periodo_de=&periodo_ate=` â€” Campina Grande vs Lagoa Seca lado a lado.
- Validado com dados reais:
  - ALVARO CORREIA DE SOUSA NETO (ago/2026): 12 protocolos, 3 reaberturas â†’ agora **dispara alerta** (regra `>=` 1).
  - MATHEUS FERNANDES DA SILVA: 12 reaberturas â†’ alerta dispara.
  - status-unidade CG: 723 abertas, 1095 produtivas, 43.36 HE (bate com cardsUnidadeHE); LAGOA SECA: 117 abertas, 11.58 HE, 1 infraÃ§Ã£o.
- Testes: 31 passed (inclui `test_calcular_alerta.py` com a calibraÃ§Ã£o nova).

### PendÃªncias

- **Achado do dashboard â€” saldo acumulado de banco de horas "Positivo +150:37 / Negativo -41:20" (concluÃ­do em 2026-08-15)**: investigado e concluÃ­do â€” **nÃ£o existe endpoint prÃ³prio** para esse saldo. Probes em `/api/saldo`, `/api/saldo-geral`, `/api/banco-horas`, `/api/bh`, `/api/extrato`, `/api/painel`, `/api/home`, `/api/cards` â†’ todos 404. `/api/analises` + `/api/semanatec` sÃ£o os Ãºnicos endpoints de dados confirmados, e as chaves documentadas de `analises` nÃ£o expÃµem saldo acumulado. **ConclusÃ£o**: o saldo Ã© **derivado no frontend** a partir do payload completo de `/api/analises` (soma de `trabalhado âˆ’ previsto` por tÃ©cnico/dia, sobre os 97 tÃ©cnicos do ciclo). EvidÃªncia: cÃ¡lculo manual no top-10 do `rankTecHE` deu +153:33/-23:20 (prÃ³ximo, mas nÃ£o exato â€” o `rankTecHE` Ã© sÃ³ o top-10 e nÃ£o traz o detalhe diÃ¡rio de todos os tÃ©cnicos). **PendÃªncia de implementaÃ§Ã£o futura**: para reproduzir esse saldo no nosso backend, precisamos ou de um payload que exponha o detalhe completo de todos os tÃ©cnicos, ou validar a fÃ³rmula com o usuÃ¡rio (definiÃ§Ã£o de "saldo", quais dias/unidades, e como o "Ant:" Ã© calculado). NÃ£o implementado â€” decisÃ£o registrada conforme regra de nÃ£o aÃ§Ã£o autÃ´noma.
- UsuÃ¡rio validar manualmente o diagnÃ³stico de um tÃ©cnico conhecido contra o que via nos painÃ©is.

## Sprint 3 â€” RecorrÃªncia (Excel + join) e InspeÃ§Ã£o (Sheets)

Status: **em andamento** (recorrÃªncia completa e validada com arquivo real; SheetsClient pronto, aguardando service account).

### Feito

- `app/etl/recorrencia.py`: ETL do analÃ­tico de recorrÃªncia.
  - Estrutura real validada em `recorrencia_2026-08_campina-grande.xlsx` (C:\Users\proxx\Downloads): aba `Analitico`, linha 0 = grupos, linha 1 = headers, dados a partir da linha 2. `header=1` com `.strip()` nas colunas.
  - Parsers robustos: `_as_str`, `_as_protocolo` (remove `.0` de float do pandas em `Protocolo`/`Protocolo anterior`), `_as_datetime`, `_as_int`.
  - Join protocoloâ†”tÃ©cnico: `_mapa_protocolo_tecnico_em_lotes` (funÃ§Ã£o pura testÃ¡vel, lote de 1000) + `_buscar_mapa_protocolo_tecnico` lendo do Postgres jÃ¡ sincronizado (sem chamar API).
  - Upsert por `protocolo` (chave Ãºnica) via `db.merge`.
- **CorreÃ§Ã£o de modelagem**: a FK `ocorrencia_recorrencia_protocolo_anterior_fkey` impedia o import â€” todos os 83 protocolos anteriores estÃ£o fora da janela de 30 dias (nÃ£o estÃ£o no arquivo). FK removida do modelo e do banco; `protocolo_anterior` virou Text informativo.
- **Import real**: 463 importadas, 83 recorrentes (bate com o manual), 4 sem tÃ©cnico (fora do lookback â€” esperado, critÃ©rio de pronto ok).
- Endpoints `app/routers/recorrencia.py`:
  - `GET /recorrencia/por-tecnico?tecnico=&periodo_de=&periodo_ate=` â€” total de protocolos e contagem `Ã©_recorrencia = SIM` no perÃ­odo.
  - `GET /recorrencia/detalhe?tecnico=&periodo_de=&periodo_ate=` â€” detalhe para conferir com o painel.
  - Validados com dados reais (ex. ALVARO...: 12 protocolos, 3 recorrentes).
- `app/services/sheets_client.py`: `SheetsClient` (gspread + service account via env `SHEETS_SERVICE_ACCOUNT_JSON`/`SHEETS_SPREADSHEET_URL`), `ler_inspecoes()`, `tecnico_valido_roster()`, `_parse_data_sheets()`. Sem credenciais, loga warning e retorna vazio (padrÃ£o do Telegram).
- `.env.example` atualizado (vars do Sheets); `requirements.txt` com `pandas`, `openpyxl`, `gspread`.
- Testes: 21 passed (ETL: parsers, estrutura do Excel, loteamento do join).

### PendÃªncias

- ValidaÃ§Ã£o manual do usuÃ¡rio: `/recorrencia/por-tecnico` bate com o que ele via no painel de recorrÃªncia.
- ~~Criar service account do Google Sheets e preencher `SHEETS_SERVICE_ACCOUNT_JSON`/`SHEETS_SPREADSHEET_URL`~~ â€” **concluÃ­do em 2026-08-16**.
- UsuÃ¡rio vai migrar para planilha online diÃ¡ria (hoje Ã© export manual local) â€” quando isso acontecer, o ETL passa a ler dessa planilha.

### IntegraÃ§Ã£o Google Sheets completa (2026-08-16)

- `SheetsClient` reescrito para leitura genÃ©rica: `listar_abas()`, `ler_aba(nome)`, `ler_todas()`. Suporta arquivo (`SHEETS_SERVICE_ACCOUNT_FILE`) ou string JSON (`SHEETS_SERVICE_ACCOUNT_JSON`).
- `credencial.json` corrigido (`client_email` continha URL da planilha em vez do email da service account). Adicionado ao `.gitignore`.
- Service account `agente-ope-sheets@agenteope.iam.gserviceaccount.com` compartilhada na planilha (editor).
- Planilha: **UNIDADE CAMPINA GRANDE _ LAGOA SECA** â€” 36 abas (COLABORADORES, BASE, BASE 3 MESES, BASE PRODUÃ‡ÃƒO, PRODUÃ‡ÃƒO, PRODUÃ‡ÃƒO MÃŠS, RESULTADO, ABERTURA, FÃ‰RIAS, ESCALAS mensais, DOUGLAS/JURACI/CARLOS, REGIÃ•ES, FERRAMENTAL, PENDENCIAS, etc.).
- Endpoint `GET /planilha/abas` (lista abas) e `GET /planilha/{aba}?limite=` (lÃª dados) â€” protegido por `exigir_token_ops`.
- Tool `getPlanilha` adicionada ao plugin `.opencode/plugins/operacoes.ts` â€” primeiro chama sem aba (lista), depois com nome da aba (dados).

## Sprint 2 â€” painel-ope (banco de horas, HE, infraÃ§Ãµes)

Status: **em andamento** (etapas 1 e 2 feitas; job, endpoints e sync real concluÃ­dos; falta validaÃ§Ã£o manual do usuÃ¡rio).

### Feito

- Etapa 1 â€” `app/services/painel_ope_client.py`: `PainelOpeClient` (httpx sÃ­ncrono, cookie via `settings.ope_session_cookie`), `_decodificar_payload_jwt` (aceita 2 segmentos `payload.sig` e JWT clÃ¡ssico 3 segmentos, prefere o que tem `exp`), `dias_para_expirar()` (`math.ceil`), `get_analises(de, ate, setor)` e `get_semanatec(setor)`; 401/403 â†’ `AuthenticationError`. Nunca loga/imprime o valor do cookie.
- Etapa 2 â€” probe real (sem tocar em banco), descobertas apresentadas e validadas com o usuÃ¡rio:
  - Setores vÃ¡lidos: `REG01`, `REG02`, `REG03`, `EXPANSAO`, `PMO`, `REDES`. **NÃ£o hÃ¡ cÃ³digo prÃ³prio para Lagoa Seca** â€” REG02 cobre Campina Grande + Lagoa Seca (filtro de unidade Ã© client-side).
  - `analises` aceita `de`/`ate` em `YYYYMMDD` (dashboard) e `YYYY-MM-DD`; aceita mÃªs inteiro (validado `20260701â€“20260731`); `periodo.modo='semana'` Ã© sÃ³ rÃ³tulo.
  - DecisÃ£o do usuÃ¡rio: sincronizar **apenas REG02**.
  - DecisÃ£o do usuÃ¡rio: modelo `infracao` ajustado ao payload real â€” **sem coluna `dias`**; campos reais: `nome`(tÃ©cnico), `sup`, `unidade`, `data`(=`dataKey`), `detalhe`(motivo), `batidas`, `previsto`, `autorizado`, `justificativa`.
- Job `app/jobs/sync_painel_ope.py`:
  - `sync_painel_ope()`: semana atual (segundaâ€“domingo) para REG02; `get_analises` â†’ upsert em `banco_horas_semanal` (unique setor+semana_de+semana_ate) + `infracoesListaSemana` â†’ `infracao` (dedup por tecnico+data+motivo, sem ID no payload); `get_semanatec` â†’ `roster_tecnico` (upsert por tÃ©cnico).
  - `start_scheduler`/`stop_scheduler`: APScheduler diÃ¡rio via lifespan (registrado no `main.py` junto ao do Proxxima); sÃ³ agenda se cookie configurado.
  - Logs apenas com contagens e estado do cookie â€” nunca o valor.
- Endpoints async `app/routers/banco_horas.py`:
  - `GET /banco-horas/analises?setor=` (e `de`/`ate` opcionais) â€” lÃª o snapshot do Postgres e extrai totais do payload. Assinatura alinhada ao critÃ©rio de pronto do roadmap (`de`/`ate`).
  - `GET /banco-horas/roster?setor=` â€” lista de tÃ©cnicos (validador de nomes).
  - `GET /banco-horas/status-cookie` â€” `{configurado, expira_em_dias}`.
- Alerta Telegram (roadmap Sprint 2, item 4):
  - `app/services/telegram.py`: `avisar_telegram()` (httpx, timeout 15s); sem token/chat configurados, loga warning e segue â€” nunca derruba o sync.
  - `app/jobs/checar_cookie.py`: `checar_expiracao_cookie()` â€” alerta quando cookie ausente, invÃ¡lido (AuthenticationError) ou `dias_para_expirar() <= 1`. Agendado diÃ¡rio junto ao sync.
  - `sync_painel_ope()`: em `AuthenticationError` (401/403), alerta via Telegram e re-levanta (falha controlada, sem contornar autenticaÃ§Ã£o).
- MigraÃ§Ã£o no banco: `infracao` perdeu `dias`; ganhou `unidade`, `sup`, `data` (TEXT/TEXT/DATE).
- Sync real (manual): semana 10â€“16/08, `he_horas=130.98` (bate com o probe), 4 infraÃ§Ãµes, roster de 100 tÃ©cnicos. Endpoints validados via TestClient (200). Testes: 9 passed.

### PendÃªncias

- ValidaÃ§Ã£o manual do usuÃ¡rio contra o dashboard (heHoras/infraÃ§Ãµes/roster de REG02).
- Preencher `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` no `.env` para ativar os alertas (hoje degradam com warning).

## Sprint 0 â€” Schema fechado + esqueleto FastAPI

Status: **em andamento** (esqueleto e schema prontos; pendÃªncias do sprint listadas abaixo).

### Feito

- Schema do Postgres fechado com base nas 4 fontes reais (validado pelo usuÃ¡rio):
  - `solicitacao_servico` (Proxxima GetAll) â€” `os` normalizado como chave de join
  - `ocorrencia_recorrencia` (Excel "AnalÃ­tico" + join de tÃ©cnico)
  - `banco_horas_semanal` + `infracao` (painel-ope `/analises`, snapshot JSONB semanal)
  - `inspecao` (Google Sheets)
  - `roster_tecnico` (validador via `/semanatec`)
- DecisÃµes tomadas com o usuÃ¡rio:
  - **Fora do schema** as tabelas de resumo diÃ¡rio do `aniel-aovivo` (`solicitacao_resumo_diario`, `metrica_recorrencia_diaria`, `metrica_produtividade_diaria`) â€” viram agregaÃ§Ãµes/views do `solicitacao_servico` no Sprint 4.
  - painel-ope guardado como **snapshot JSONB por semana**; colunas normalizadas (HE, infraÃ§Ãµes, rankings) sÃ³ depois de ver um payload real.
- Esqueleto FastAPI criado (sem lÃ³gica de negÃ³cio):
  - `app/config.py` (pydantic-settings, segredos sÃ³ via env), `app/db.py` (engine/session/Base/get_db)
  - `app/models/` com os 6 modelos SQLAlchemy (DDL compilado e conferido)
  - `app/routers/` (`/health`), `app/schemas/`, `app/services/`, `app/etl/`, `app/jobs/` (vazios, nomes conforme roadmap)
  - `app/main.py`, `.gitignore`, `.env.example`, `requirements.txt`, `tests/`
- venv `.venv` criada com deps instaladas (FastAPI, SQLAlchemy 2, psycopg3, pydantic-settings); import do app verificado.

### PendÃªncias do Sprint 0 (do roadmap)

- Mapear campos internos de `analises` (HE, infraÃ§Ãµes, rankings) com um payload real â€” para definir as colunas normalizadas do painel-ope.
- Confirmar janela de datas aceita por `analises`/`semanatec` (semana vs mÃªs inteiro).
- Criar conta de serviÃ§o do Google Sheets (sÃ³ necessÃ¡ria para InspeÃ§Ã£o).
- Testar decodificaÃ§Ã£o do cookie `ope_session` (JWT base64) e montar o alerta de renovaÃ§Ã£o.

### ObservaÃ§Ãµes

- AGENTS.md referencia `docs/roadmap.md`, mas o arquivo real Ã© `docs/roadmap-agente-decisao-operacional.md` â€” tratÃ¡-lo como fonte de verdade.
- Commit `eda9a15` = Sprint 0. `/health` foi decouplado do banco (nÃ£o hÃ¡ Postgres local) â€” resposta `{"status":"ok"}` validada via uvicorn.

## Sprint 1 â€” FundaÃ§Ã£o + Proxxima

Status: **concluÃ­do** (sync validado com janela de 30 dias; aguarda validaÃ§Ã£o manual do usuÃ¡rio contra o painel).

### Feito

- `app/services/proxxima_client.py` portado do `proxxima-dashboard` (diff revisado: sÃ³ imports/config mudaram; lÃ³gica de login, token anti-forgery e `GetAll` intacta).
  - Credenciais agora via `settings.proxxima_user`/`proxxima_password` (env), URLs como constantes no mÃ³dulo, `DEFAULT_LOOKBACK_DAYS = 30`.
- DivergÃªncia roadmapÃ—client resolvida com o usuÃ¡rio: payload do `GetAll` **Ã© superconjunto** com as chaves do roadmap (`os`/`tecnico`/`uni`/`nat`/`status`/`abertura`/`venc`/`slaTxt`/`relatos` â€” o `COLUMNS_DATA` sÃ³ pede as colunas da tela; o response traz mais).
- **PÃ¡gina de login mudou** (Connect v1.15.2.33): nÃ£o tem mais `__RequestVerificationToken`. Client adaptado â€” token opcional (loga warning e segue), mantÃ©m suporte caso volte.
- De-para payloadâ†’modelo validado com o usuÃ¡rio: `os`=`numero_Obra` split "/", `os_original`=`numero_Obra`, `unidade`=`grupo_Area`, `natureza`=`natureza`, `status`=`status_Execucao`, `tecnico`=`responsavel` (nome maiÃºsculo), `abertura`/`venc`=`dataHora_Abertura_OS`/`dataHora_Vencimento_OS` (BRâ†’datetime), `sla_status`=`sla`, `relatos`=`observacao`.
- DefiniÃ§Ã£o de **OS aberta** aprovada: status nÃ£o comeÃ§a com "Fechada" e nÃ£o Ã© "Cancelado".
- Job `app/jobs/sync_proxxima.py`: upsert em `solicitacao_servico` por `os_original`, em lotes de 1000 (PostgreSQL limita a ~65535 params/statement), APScheduler 30 min via lifespan (nÃ£o roda em teste manual).
- **DecisÃ£o de modelagem**: `numero_Obra` pode ter sub-ordens (`8722521/4`, `8671912/2`); a chave Ãºnica do upsert passou de `os` para `os_original` (= `numero_Obra` completo), mantendo todas as sub-ordens. `os` (base) virou coluna de join/agrupamento com Ã­ndice.
- Endpoints async `GET /solicitacoes/resumo?unidade=` e `GET /solicitacoes/por-tecnico?tecnico=` â€” leitura apenas do Postgres; sem chamada externa no request.
- Sync real (janela 30 dias): 25.769 registros, 0 NULL de tÃ©cnico, paginaÃ§Ã£o ~52 pÃ¡ginas, tempo ~3 min. ExecuÃ§Ã£o manual isolada (scheduler nÃ£o ativado).

### PendÃªncias

- ValidaÃ§Ã£o final do usuÃ¡rio: `por-tecnico`/`resumo` de dados reais batem com o painel (ex.: tÃ©cnico real + unidade REG-CAMPINA GRANDE).
- Quando validar e ligar o agendamento de produÃ§Ã£o, subir uvicorn (que ativa o scheduler via lifespan).

### ObservaÃ§Ãµes

- Commit `eda9a15` = Sprint 0. Sprint 1 commitado apÃ³s validaÃ§Ã£o do sync de 30 dias.
- `httpx` e `apscheduler` adicionados ao `requirements.txt`.

## Fase 4 â€” Cron de resumo e alertas no Hermes (2026-08-28)

Status: **implementado e validado ponta a ponta** (entrega no Telegram confirmada nos logs do gateway; aguarda confirmaÃ§Ã£o visual do usuÃ¡rio).

### Feito

- 3 jobs criados no `hermes cron` (scheduler do gateway, UTC-3):
  - `94a08eebbd48` â€” **Resumo Diario OPE (07:30)**: `30 7 * * *`, entrega `telegram:6664094468`. Prompt: resumo diÃ¡rio com `get_tempo_real` (2 unidades) + `getStatusUnidade` (semana) â€” panorama agora (por natureza, destaque SEM ACESSO, SLA vencido, sem tÃ©cnico), fechadas hoje, HE e recorrÃªncias da semana; nÃºmeros primeiro, consultivo, encerra com decisÃ£o do coordenador.
  - `d3c002570220` â€” **Varredura Alertas OPE (09h)**: `0 9 * * *`, `--continuity`. Limites calibrados do Sprint 4: recorrÃªncia â‰¥1 reabertura, HE > 8h, inspeÃ§Ã£o < 7.0 (planilha via `getPlanilha`; se 503, informa indisponÃ­vel).
  - `f09fa0260230` â€” **Varredura Alertas OPE (17h)**: `0 17 * * *`, `--continuity` (mesmo prompt da manhÃ£). Primeiro disparo real: **28/08 Ã s 17:00**.
- **Aprendizados de entrega** (importantes):
  - `deliver=telegram` (sem chat) criado via CLI nÃ£o resolve alvo â†’ usar **`telegram:6664094468`** explÃ­cito (`no delivery target resolved for deliver=telegram`).
  - **NÃƒO usar `hermes cron run` via ssh** para validar: o processo dono da execuÃ§Ã£o Ã© o CLI e morre quando a sessÃ£o ssh fecha â†’ execuÃ§Ã£o vira `unknown` e a entrega se perde (`Reclaimed 1 cron execution(s) whose owner process died`). Runs reais rodam no processo do gateway (dono estÃ¡vel) â€” exemplos `source=builtin` de 12:06/12:08 completando e entregando (`delivered to telegram:6664094468 via live adapter`).
  - ValidaÃ§Ã£o por tick real: editar schedule para `*/2 * * * *`, observar o gateway disparar, e reverter â€” funcionou.

### ValidaÃ§Ã£o ponta a ponta

- Run de teste 12:06: job completou com 2694 chars; log do gateway: `12:07:23 delivered to telegram:6664094468 via live adapter`.
- Run extra 12:08 (tick residual antes do revert) tambÃ©m entregue â€” usuÃ¡rio deve ter recebido **dois** resumos no Telegram (~12:07 e ~12:09).

### PendÃªncias

- **Renovar cookie do painel OperaÃ§Ãµes ~a cada 4 dias** (expira 2026-09-01 17:05) â€” job alerta no Telegram se expirar.
- ConfirmaÃ§Ã£o visual do usuÃ¡rio (mensagens ~12:07/12:09 no bot).
- Observar o primeiro disparo automÃ¡tico da **varredura das 17:00** de 28/08.
- InspeÃ§Ã£o na varredura depende da credencial do Sheets na AWS (pendÃªncia conhecida).
- **DecisÃ£o de domÃ­nio pendente**: atribuir recorrÃªncia ao tÃ©cnico da **OS atual** (feito hoje, validado) ou ao tÃ©cnico da **OS anterior** (quem causou a reabertura) â€” questionar o coordenador antes de mudar.

## CorreÃ§Ã£o: rÃ³tulo de recorrÃªncia no diagnÃ³stico por tÃ©cnico (2026-08-28)

### Problema relatado

O agente respondeu que ALVARO CORREIA tinha 22 recorrÃªncias em agosto e que isso
"concentrava 100% das recorrÃªncias de CG num Ãºnico tÃ©cnico". O coordenador negou:
hÃ¡ recorrÃªncias de vÃ¡rias equipes.

### InvestigaÃ§Ã£o (dados reais no Postgres)

- **A atribuiÃ§Ã£o JOIN estava CORRETA**: 33 tÃ©cnicos distintos tÃªm recorrÃªncia em CG
  em ago/2026 (total 195). ALVARO CORREIA DE SOUSA NETO tem **4 recorrÃªncias**.
- **Raiz do erro**: o campo JSON `recorrencia_total_protocolos` contava **todas as OS
  do tÃ©cnico no analÃ­tico** (22 â€” inclui as nÃ£o-recorrentes), nÃ£o as recorrÃªncias.
  O nome induzia o LLM a ler "22 protocolos com recorrÃªncia" e a montar a narrativa.

### CorreÃ§Ã£o aplicada

- Schema `DiagnosticoTecnico`: `recorrencia_total_protocolos` renomeado para
  `recorrencia_os_no_analitico` + novo campo `recorrencia_contexto` (frase explÃ­cita:
  quantas OS no analÃ­tico e quantas sÃ£o recorrÃªncia).
- DescriÃ§Ã£o da tool `getDiagnosticoTecnico` no plugin: documenta que para recorrÃªncias
  do tÃ©cnico o campo certo Ã© `recorrencia_reaberturas`.
- 131 testes verdes. Fix commitado junto.

## Ranking de recorrÃªncia e quebra por problema (2026-08-28)

Status: **implementado e com testes** (aguarda deploy + validaÃ§Ã£o no bot).

### Contexto

O bot (Hermes) nÃ£o conseguia responder "5 maiores ofensores de recorrÃªncia" nem
"recorrÃªncia por natureza": as tools MCP nÃ£o tinham ranking e o agente nÃ£o tem
como listar tÃ©cnicos sozinho. Os dados jÃ¡ estavam no Postgres.

### Feito

- `GET /recorrencia/ranking?unidade&periodo_de&periodo_ate&top=5` â€” agrega
  `Ã©_recorrencia=SIM` por tÃ©cnico numa Ãºnica query: `recorrencias` (a mÃ©trica),
  `os_no_analitico` (sÃ³ contexto, para nÃ£o repetir o erro de rÃ³tulo), `taxa`,
  `total_recorrencias` da unidade e top (1â€“20). Exclui tÃ©cnicos sem join.
- `GET /recorrencia/por-problema?unidade&periodo_de&periodo_ate` â€” contagem de
  recorrÃªncias por `problema_fechamento` + `resumo_categorias` em 3 grupos macro
  (`categorizar_problema`: administrativo = CLIENTE DESISTIU/EM MASSIVA,
  rede_externa = ORIGEM REDES/INFRA, default = culpa_do_campo â€” ajustÃ¡vel).
- Tools MCP novas (`app/services/mcp_server.py`): `get_ranking_recorrencia` e
  `get_recorrencia_por_problema` (o bot do Telegram vÃª estas). Espelhadas no
  plugin `.opencode/plugins/operacoes.ts`.
- Testes: `tests/test_recorrencia_endpoints.py` (categorizaÃ§Ã£o + agregaÃ§Ãµes com
  fake DB) e MCP atualizado (7 tools + URLs). **152 passed**.

### PendÃªncias

- Deploy AWS + curl de validaÃ§Ã£o (esperado: ranking CG/ago com MATHEUS 23
  primeiro e ALVARO 4; por-problema com CONECTOR 48 encabeÃ§ando).
- ValidaÃ§Ã£o do usuÃ¡rio no bot ("quais os 5 tÃ©cnicos com mais recorrÃªncias em CG
  na semana?"; "recorrÃªncias por natureza em CG").

## Rota Painel OperaÃ§Ãµes â€” recorrÃªncia sem planilha (2026-08-28)

Status: **implementado, testado ao vivo e importado na AWS** (aguarda validaÃ§Ã£o
do usuÃ¡rio no Telegram/consultas).

### Contexto

- O painel `operacoes.proxxima.net` (server-rendered) tem a recorrÃªncia **por
  protocolo** na pÃ¡gina `/painel/recorrencia/analitico?mes=YYYY-MM&unidade=UNIDADE X`,
  que **baixa o mesmo Excel "AnalÃ­tico" do export manual** (aba `Analitico`, 1.028
  linhas CG em ago/2026 vs 463 do export antigo).
- **Auth = Zoho SSO** (sem usuÃ¡rio/senha de API; pÃ¡gina `/login` confirma) â†’
  acesso programÃ¡tico pelo **cookie `bl_session`** (mesmo padrÃ£o do painel-ope).

### Feito

- `OPERACOES_SESSION_COOKIE` no `app.config.Settings` (o valor real sÃ³ no `.env`
  da AWS; validade atÃ© 2026-09-01 17:05).
- `app/services/operacoes_client.py`: `OperacoesClient.fetch_analitico(unidade, mes)`
  â†’ bytes do xlsx; detecta expiraÃ§Ã£o (303/`/login`); valida magic `PK`;
  URL form-urlencoded (`UNIDADE+CAMPINA+GRANDE`).
- `app/jobs/sync_recorrencia_painel.py`: baixa CG+LS do mÃªs corrente, grava em
  temp, reusa **`importar_recorrencia`** (parser sem mudanÃ§a â€” 13 colunas
  esperadas presentes no painel), remove temp, **alerta Telegram** se o cookie
  expirar (relanÃ§a `OperacoesAuthError`, nunca contorna auth). Scheduler diÃ¡rio
  **06:15 UTC-3** (guard: cookie presente; wiring no `main.py`).
- Testes: `test_operacoes_client.py` (6) + `test_sync_recorrencia_painel.py` (3).
  **131 passed** no total. Commit `c095bd0`.

### ValidaÃ§Ã£o ao vivo (AWS, 28/08 ~18:58 UTC-3)

```
UNIDADE CAMPINA GRANDE: importadas 1029, sem_tecnico 13, com_recorrencia 195
UNIDADE LAGOA SECA:      importadas 329, sem_tecnico 2, com_recorrencia 36
```

Banco confirmado: CG 1.029 / LS 329 em `ocorrencia_recorrencia`.

### PendÃªncias / observaÃ§Ãµes

- **Renovar cookie ~a cada 4 dias** (expira 2026-09-01 17:05) â€” alerta do job
  avisa se expirar; renovar Ã© recapturar o `bl_session` no navegador.
- Planilha (Sheets) continua pendente **sÃ³ para inspeÃ§Ã£o**.

### Atendimentos agendados por dia/natureza (proxima)

### Contexto

- A pergunta "quantos atendimentos temos agendado para amanha?" nao podia ser
  respondida: o bot afirmava que "nao existe campo" (fonte letalmente errada —
  ele so olhava o endpoint tempo-real). O GetAll do Painel_ServicosSEMPRE
  teve o campo **data_Hora_Agendamento_OS** (ex.: `29/08/2026 09:55`),
  gravado no payload bruto desde a Fase 1; so nao estava exposto.
- `data_Hora_Agendamento_OS` vazio = OS ainda "Aberta Aguardando Agendamento"
  (fila SEM data), conceito oposto ao agendado. Status "Aberta Aguardando
  Atendimento" = ja agendada.

### Feito

- Coluna gendamento (timestamptz) em solicitacao_servico (modelo +
  _map_payload do sync_proxxima).
- Endpoint **GET /diagnostico/agendados/{unidade}?data=YYYY-MM-DD**
  (_agendados_por_dia): total, com/sem equipe e quebra por natureza. "Com
  equipe" = tecnico responsavel OU equipe_Matricula do payload. Inclui so OS
  abertas (exclui Fechadas/Cancelado). Cast de data em America/Sao_Paulo.
- Tool MCP **get_atendimentos_agendados** (padrao: AMANHA quando data omitido).
- Migracao/backfill na AWS: `ALTER TABLE ... ADD COLUMN agendamento` +
  `UPDATE ... to_timestamp(payload->>'data_Hora_Agendamento_OS')`; 21.879 com
  agendamento / 3.023 sem. Commit `5a82986`.
- Testes: 	est_agendados.py (10) + 	est_mcp_server.py 8 tools. **163 passed**.

### Validacao ao vivo (AWS, 28/08 ~23:20) — data 29/08/2026

`
CAMPINA GRANDE: total 53, com_equipe 50, sem_equipe 3
  INSTALACAO 25 (equipe 24) | SEM ACESSO 11 (11) | CORRETIVO 8 (8) |
  CORRETIVA/AP. 6 (6) | RECOLHIMENTO 2 (0) | MUDANCA END 1 (1)
LAGOA SECA: total 34, com_equipe 30, sem_equipe 4
  CORRETIVA/AP. 11 (11) | SEM ACESSO 9 (9) | INSTALACAO 5 (5) |
  RECOLHIMENTO 4 (0) | CORRETIVO 3 (3) | MUDANCA END 2 (2)
`

### Pendencia

- Bot: sessao do Telegram precisa de **/new** para a sessao ativa reenumerar
  as 8 tools MCP (a sessao congela o toolset na criacao; restart do gateway nao
  atualiza sessao existente). O processo MCP ja roda o codigo novo.

## Pontuação por dia das equipes (n8n aniel-aovivo) — 2026-08-29

Status: **implementado + testado local** (aguarda deploy AWS e validação do
usuário). Commit: em andamento.

### Contexto / decisões do usuário

- Pergunta que o agente não sabia responder: "pontuação por dia das equipes".
  Meta definida pelo usuário: **8 pontos/dia de SEG a SEX** (sábado/domingo
  **sem meta**) e **40 pontos/semana** (semana = SEG a DOM). Cada técnico = uma
  equipe.
- Fonte confirmada com o usuário: **painel n8n `n8n.proxxima.net`** (webhooks
  públicos, sem auth) — HAR fornecido por ele. O webhook **`/webhook/aniel-aovivo`**
  traz `fechSemana`: fechamentos da semana com `os`, `tecnico`, `uni`, `encDK`
  (dia YYYYMMDD) e **`pontos`** por OS. **Pontuação do dia da equipe = soma dos
  `pontos` dos fechamentos do dia.** Validação com o HAR: CG segunda = 160.54
  (idêntico ao webhook ao vivo, `geradoEm 29/08/2026 11:30`).
- `naoPontua` do payload = lista de técnicos que não participam (flag exposta,
  não filtra a resposta — o agente decide).
- Cobertura: CG 172 / LS 41 linhas (técnico×dia) só para a semana atual —
  pontuação é proteção do momento, não histórico (para histórico seria TOTVS
  2837323, que segue com `metrica_totvs` vazia).

### Feito

- `app/models/pontuacao_tecnico_dia.py`: tabela `pontuacao_tecnico_dia`
  (tecnico, unidade, data, pontos Numeric(6,2), nao_pontua; unique
  (tecnico, unidade, data)); criada via `create_all` no boot.
- `app/services/aniel_client.py`: `AnielClient.fetch_aovivo()` (GET público,
  valida chaves esperadas e o formato de `fechSemana`, loga contagens) +
  `sumarizar_pontuacao()` (função pura soma por tecnico/unidade/dia).
- `app/jobs/sync_pontuacao.py`: job **de 1h** (`next_run_time` imediato) →
  baixa o aovivo, `_montar_linhas` soma+arredonda+flag `nao_pontua` filtrando
  pela semana BR (SEG–DOM), upsert `ON CONFLICT (tecnico, unidade, data)`.
  Default do dia usa `America/Sao_Paulo` (não UTC).
- Endpoint `GET /diagnostico/pontuacao/{unidade}?data=` (`_agregar_pontuacao`):
  por técnico, `pontos_dia` + `meta_dia` (None sáb/dom) + `cumpre_meta_dia`,
  `ponto_semana` + `cumpre_meta_semana`, quebra diária `dias[]`, ordenado por
  semana desc. Totais do dia/semana da unidade. Parâmetro **`resumo=true`**
  omite `dias[]` (o payload cheio de CG = 43 equipes × 7 dias ≈ 68 KB numa
  linha, que o leitor do Hermes truncava — o resumo deixa ~6 KB legível).
- Tool MCP **get_pontuacao_equipe** (total: 9 tools) com **`resumo=true` por
  padrão** (`resumo=false` traz o detalhe por dia). Wiring no `main.py`.
- Testes novos: `test_aniel_client.py` (7), `test_pontuacao_sync.py` (7),
  `test_pontuacao_endpoint.py` (10), MCP atualizado para 9 tools (3 novos).
  **191 passed** (antes 165). Validação ao vivo (GET público): soma de CG na
  segunda = 160.54, batendo com o HAR.

### Pendências

- Deploy AWS: `git push` local → servidor `git pull` → restart
  (`agente-ope` + `hermes-gateway`) → curva ao vivo do sync e validação com o
  usuário (ex.: pontuação de MATHEUS FERNANDES DA SILVA vs painel TOTVS/n8n).
- Bot: sessão ativa precisa de **/new** para ver a 9ª tool (padrão recorrente).
- Retro: primeiro uso real do bot mostrou que a resposta de CG (68 KB numa
  linha única, `dias[]` de 43 equipes) estourava o leitor do Hermes — corrigido
  com `resumo=true` por padrão na tool; refazer a pergunta após o deploy.

## Encerradas por natureza e por dia no período (coluna `fechamento`) — 2026-08-29

Status: **implementado, testado (201 passed) e deployado na AWS**.

### Contexto / decisões do usuário

- Ao pedir o "encerrado de solicitações da semana" das duas unidades, o bot
  respondeu com o panorama por **tipo** (produtivas/improdutivas) e foi
  transparente sobre a limitação: `get_status_unidade` **não quebra encerradas
  por natureza**. Usuário pediu para tratar a limitação e gerar o relatório mais
  completo.
- Métrica nova: "encerradas no período" = fechadas na janela pela **data de
  ENCERRAMENTO** (`dataHora_Encerramento_OS`, novo campo `fechamento`), não pela
  data de abertura como o status-unidade. O corte por dia/ano usa
  `America/Sao_Paulo`. **Recolhimento aparece como natureza própria** (transparente
  no detalhamento — sem exclusão silenciosa; o agente decide como narrar).

### Feito

- `app/models/solicitacao_servico.py`: coluna **`fechamento`** (timestamptz,
  indexada). `app/jobs/sync_proxxima.py::_map_payload` agora mapeia
  `dataHora_Encerramento_OS → fechamento` (upsert já atualiza nas próximas
  execuções).
- Endpoint **`GET /diagnostico/encerradas/{unidade}?periodo_de=&periodo_ate=`**
  (`_encerradas_por_periodo` em `app/routers/diagnostico.py`): total encerradas
  (Fechada Produtiva + Fechada Improdutiva), canceladas à parte, taxa de
  produtividade (prod/(prod+impr)), **`por_natureza`** (total/prod/impr/canc,
  ordenado por total desc) e **`por_dia`**. Filtra por `fechamento`; fallback
  para `abertura` quando sem encerramento. Schemas em `app/schemas/diagnostico.py`
  (`EncerradasResumo`, `EncerradaNatureza`, `EncerradasPorDia`).
- Tool MCP **`get_encerradas_periodo`** (total: **10 tools**), period default =
  semana atual. `tests/test_encerradas.py` (5) + MCP atualizado. **201 passed**.
- Migração AWS: `ALTER TABLE ... ADD COLUMN fechamento` + índice + backfill via
  `to_timestamp(payload->>'dataHora_Encerramento_OS')` (formato min e min:seg).
  Resultado: 20.194 fechadas, **todas com `fechamento`** preenchido; 0 órfãs.

### Validação ao vivo (29/08 ~13:50 UTC-3), semana 24–30/08

- **CG**: 568 encerradas (493 prod / 75 impr, taxa 86,8%) — INSTALAÇÃO 269,
  SEM ACESSO 150, MUDANÇA END 49, CORRETIVO 44, CORRETIVA/AP 33, RECOLHIMENTO 13…
- **LS**: 133 encerradas (121 prod / 12 impr, taxa 91,0%) — SEM ACESSO 41,
  INSTALAÇÃO 37, RECOLHIMENTO 22…
- Os números **diferem do panorama anterior do bot** (CG 385 / LS 113), que
  contava fechadas pela **abertura** no período. Aqui o corte é pela **data de
  encerramento** — validar com o painel de fechadas da semana qual referência o
  usuário considera "encerradas".

### Pendências

- Validar com o painel de fechadas da semana se o corte por `fechamento`
  (CG 568 / LS 133) é o esperado, vs. o corte por abertura (385/113) do
  status-unidade — se divergir, documentar qual usar por contexto no relatório.
- **SEGURANÇA**: durante a validação, o token `OPS_API_TOKEN` apareceu impresso
  na saída de um comando (`subprocess.CalledProcessError` exibiu o header curl).
  Sinalizado ao usuário (regra de credencial) — **trocar o token**. No futuro,
  curl via urllib sem exibir args, e scripts `.sh` com line endings LF (o CRLF
  do Windows quebrou caminhos no servidor).

## Sprint 8 - Banco de Horas via planilha publica (substitui painel-ope)

Status: implementado, testado (233 passed) e **deployado na AWS em 30/08** com validacao ao vivo contra a planilha (saldos batem).

Decisoes do usuario (2026-08-30):
- Metrica: **saldo** do banco de horas (coluna SALDO do CSV).
- Dados: usar todos ate 30/07 (HISTORICO); na pratica a aba ja tem linhas ate 29/08.
- Integracao: **substituir painel-ope para banco/HE** - doravante banco de horas/HE
  vem da planilha publica (sem cookie); painel-ope fica so para infracoes.

### Feito

- `app/models/banco_horas_saldo.py`: nova tabela (tecnico, unidade, data, saldo,
  cargo, tipo, coordenador, supervisor, variacao, status; unique tecnico+unidade+data).
- `app/services/banco_horas_sheets_client.py`: client publico (CSV pub, sem cookie),
  validacao de colunas obrigatorias, parse SALDO brasileiro ("7,55"/"1.234,56") e
  DATA dd/mm/yyyy, decodificacao tolerante (utf-8-sig/utf-8/cp1252).
- `app/jobs/sync_banco_horas_saldo.py`: job diario (upsert por tecnico+unidade+data),
  filtra so CG/LS (aba HISTORICO_REG03 contem outras unidades). Agendado no main.py.
- `app/services/cruzamento.py`: `buscar_ultimos_saldos` (subquery MAX por tecnico,
  portavel), `buscar_saldo_banco_unidade`, `buscar_banco_horas_tecnico` agora retorna
  `saldo` (substitui `he_horas`) + mantem `infracoes` do painel-ope. `_calcular_alerta`
  usa `LIMITE_BANCO_HORAS=8.0` (era LIMITE_HE_SEMANAL).
- Endpoints: `GET /banco-horas/saldo/{unidade}` e `/banco-horas/saldo/tecnico/{nome}`.
- Tool MCP **`get_banco_horas_saldo`** (total: **11 tools**).
- Schema `DiagnosticoTecnico`/`StatusUnidade`: `he_horas` renomeado para
  `saldo_banco_horas`. Relatorio .docx: secoes HE -> saldo (top saldo, risco
  combinado saldo+recorrencia, indicador "Saldo Banco de Horas").
- `tests/test_banco_horas_saldo.py` (25): parse client, _montar_registros, helpers
  de cruzamento com sqlite real. Alertas/relatorio/MCP atualizados.

### Validacao ao vivo (30/08) do CSV publico
- 3.843 linhas totais; 1.908 alvo (CG 1.464 + LS 444); 1.935 outras unidades
  (FILADELFIA, JACOBINA etc. - descartadas). Datas 18/05/2026 a 29/08/2026.
  Nenhuma linha sem DATA ou SALDO nas unidades-alvo.

### Pendentes
- ~~Deploy AWS: `Base.metadata.create_all` cria a tabela; rodar `sync_banco_horas_saldo`~~
  ~~uma vez para popular (o job diario agendado so roda apos 24h).~~
- ~~Validar saldos no diagnostico/relatorio contra a planilha (o usuario bate os numeros).~~
- 401 do painel-ope: **resolvido** (cookie renovado pelo usuario em 30/08) - infracoes sincronizando.

### Deploy AWS (30/08) - F E I T O
- Push `f8f694b` (#feat banco de horas planilha publica) + `ec97fd7` (fix saldo sem
  periodo). Git pull no servidor, restart `agente-ope.service` (active, health ok) e
  `hermes-gateway` (active).
- `create_all` criou `banco_horas_saldo`; sync manual gravou **1.908** registros
  (CG 1.464 + LS 444), sem linha descartada por dado faltante.
- Fix de bug em producao: `buscar_ultimos_saldos` quebrava (`data >= None`) quando
  o endpoint `/banco-horas/saldo/...` era chamado sem `de`/`ate` - agora usa o banco
  inteiro (teste novo `test_saldo_sem_periodo_usa_banco_inteiro`).
- Validacao contra a planilha (extrai o CSV ao vivo): ALVARO CORREIA 29/08 = **-1,13
  NEGATIVO** (bate com o endpoint), BRENDO JUSTINO 29/08 = **-0,43 NEGATIVO**,
  ALEF JOHAN = 0 (ultimo 18/07, sem linhas apos). CG total 128,5h / LS 22,69h.
- `checar_expiracao_cookie` agora sonda a sessao no servidor (`/semanatec`) alem do
  `exp` do JWT - detecta sessao invalidada (caso real: exp +10d com /analises 401)
  e alerta no Telegram no mesmo dia. Teste novo `tests/test_checar_cookie.py` (6).
- Total da suite: **233 passed** (antes do deploy). TOTVS: confirmado desativado por
  commit d6d586c (fonte abandonada) - cookie ausente e esperado, sem acao.

### Cookie do painel-ope renovado (30/08)
- Usuario renovou via login Zoho; novo `OPE_SESSION_COOKIE` aplicado no `.env` da AWS
  (LF mantido, chmod 600, valor nunca logado). `exp` 10 dias (09/09/2026).
- `painel-ope_client`: timeout do client **15s -> 60s** (`HTTP_TIMEOUT`) - /analises
  passava de 15s em cold start do Vercel (ReadTimeout real com cookie valido).
  Teste novo `test_timeout_longo_para_cold_start`.
- Fix de bug real na sync de infracoes: `_parse_data_key` usava `date.strptime`
  (nao existe; quebrava toda a sync apos o login). Corrigido para
  `datetime.strptime(...).date()` + `tests/test_sync_painel_ope.py` (6).
- Sync validado ao vivo: semana 24-30/08 -> **16 infracoes**, snapshot 174,32h HE,
  roster 104 tecnicos. Endpoint `/banco-horas/analises` e `/status-cookie` OK.
- Suite apos fixes: **241 passed**.

### Resposta do bot (hermes-gateway) voltando a funcionar (30/08)
- O erro "Provider authentication failed" do bot NAO era o deploy nem o cookie: era o
  provider LLM do hermes. O gateway usa o provider **keyless** `opencode-free`
  (`https://opencode.ai/zen/v1`, sem chave); o modelo configurado `hy3-free` foi
  **removido do relay** -> `Model hy3-free is not supported` para toda mensagem.
- Sonda ao vivo de GET/POST /zen/v1/models (anonimo): `hy3-free` delisted;
  `x-preview-f-free`/`mimo-v2.5-free` UA-gated; a maioria dos free models com
  upstream indisponivel no momento; **`nemotron-3.5-lightning-free` respondeu OK**.
- `~/.hermes/config.yaml`: `model.default: hy3-free` -> `nemotron-3.5-lightning-free`
  (+ `base_url` alinhado ao zen/v1 do provider). Backup criado. Restart do
  hermes-gateway: ativo, sem erro de provider, NRestarts=0.
- Pendencia: usuario confirmar no Telegram que o bot responde normalmente.
