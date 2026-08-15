# Progresso — Agente de apoio à decisão operacional

Última atualização: 2026-08-15

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
