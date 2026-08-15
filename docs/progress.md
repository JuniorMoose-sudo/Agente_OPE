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
- Repo git tem mudanças não commitadas (docs movidos para `docs/`). Nada foi commitado.

## Próximo sprint

Sprint 1 — Fundação + portar `proxxima_client.py` (`app/services/proxxima_client.py`), job APScheduler de sync (30 min), endpoints `GET /solicitacoes/resumo` e `GET /solicitacoes/por-tecnico`.
