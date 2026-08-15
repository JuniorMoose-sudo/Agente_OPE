# Agente de Apoio à Decisão Operacional

## O que é este projeto

Backend + agente consultivo que cruza dados operacionais de uma unidade de telecom (Campina Grande e Lagoa Seca) — recorrência, produtividade, banco de horas/HE, infrações e inspeção — para responder perguntas em linguagem natural e gerar relatórios, eliminando a necessidade de abrir várias telas/planilhas manualmente antes de tomar uma decisão.

**Modo de operação: puramente consultivo.** O agente nunca executa ações automáticas nem toma decisões — só lê, cruza, calcula e explica. Qualquer funcionalidade que implique ação autônoma (alertas proativos além dos já definidos, escrita em sistemas externos, etc.) exige confirmação explícita do usuário antes de implementar, mesmo que pareça uma extensão natural do projeto.

## Onde estão as instruções detalhadas

O roadmap completo (sprints, exemplos de código, schemas, critérios de pronto) está em `docs/roadmap.md`. **Leia esse arquivo antes de começar qualquer tarefa de desenvolvimento** — ele é a fonte de verdade sobre o que construir e em que ordem. Este AGENTS.md complementa o roadmap com convenções e regras operacionais; não repete o conteúdo dele.

Progresso é rastreado em `docs/progress.md`. Ao concluir uma tarefa ou sprint, atualize esse arquivo antes de encerrar a sessão — isso é o que permite que a próxima sessão retome de onde parou sem precisar reconstruir contexto perguntando ao usuário.

## Ordem de trabalho

Siga os sprints do roadmap em ordem. Não pule etapas mesmo que pareçam simples de adiantar — a ordem existe porque cada sprint depende de dados validados no anterior (ex: os endpoints de cruzamento do Sprint 4 pressupõem que as três fontes já estão sincronizadas e confiáveis). Se identificar um atalho genuíno, explique o porquê antes de tomar a decisão, não decida silenciosamente.

Antes de considerar um sprint concluído, verifique o "critério de pronto" descrito no roadmap para aquele sprint — não é suficiente o código rodar sem erro, o resultado precisa bater com o que o usuário já sabe manualmente (ele vai validar contra o que via nos painéis).

## Fontes de dados — resumo rápido

| Fonte | Tipo | Autenticação | Observação |
|---|---|---|---|
| `Painel_ServicosApi/GetAll` (Proxxima) | API | Login ASP.NET (token anti-forgery + cookies) | Client já existe, portar de `proxxima_client.py`, não reescrever |
| `painel-ope.vercel.app` | API | Cookie de sessão, expira ~7 dias | Verificar expiração do JWT antes de cada uso; alertar via Telegram se perto de expirar |
| Excel de recorrência ("Analítico") | Export manual | — | Sem coluna de técnico; enriquecer via join `Protocolo` = `os` do GetAll |
| Google Sheets (Inspeção) | Planilha | Service account | Único domínio 100% manual |

Chave de identificação de técnico em todo o sistema: **nome completo em maiúsculas**, como as APIs já usam — não criar ID numérico artificial.

## Regras de segurança — não negociáveis

- Nunca hardcode usuário, senha, cookie, token ou qualquer segredo em código, mesmo em exemplos ou testes. Sempre variável de ambiente (`.env`, nunca commitado) ou secrets manager.
- Nunca logar ou imprimir o valor de uma credencial, mesmo em modo debug.
- Ao lidar com erro de autenticação (401/403), o comportamento correto é alertar (Telegram) e falhar de forma controlada — nunca tentar contornar a autenticação de outra forma.
- Se em algum momento uma credencial real aparecer em um arquivo, commit, ou log por engano, sinalize isso ao usuário imediatamente para que ele possa trocá-la — não assuma que "não teve problema porque é ambiente local".

## Convenções técnicas

- **Separação sync/serve**: jobs de ingestão (que chamam APIs externas, login, parsing de Excel/Sheets) rodam de forma síncrona via APScheduler, fora do ciclo de request. Endpoints FastAPI são `async` e só leem do Postgres já populado — nunca chamam uma API externa dentro do tempo de resposta de um endpoint que o agente consulta.
- **Parsers de payload externo são o ponto mais frágil do sistema** (formato pode mudar sem aviso). Sempre validar campos esperados explicitamente (`assert` ou checagem equivalente) e logar quantos registros foram processados/ignorados a cada execução.
- Testes (`pytest`) são obrigatórios para: lógica de cálculo de alerta (`_calcular_alerta` e afins), parsers de payload, e a lógica de join protocolo↔técnico.
- Nomenclatura de arquivos e módulos segue o que já está no roadmap (`app/services/proxxima_client.py`, `app/services/painel_ope_client.py`, `app/etl/recorrencia.py`, etc.) — não reorganizar a estrutura sem necessidade.

## O que perguntar antes de agir

- Antes de rodar qualquer sync contra uma API real (Proxxima, painel-ope) fora de teste controlado, confirme com o usuário — essas chamadas usam credenciais de produção de um sistema corporativo real.
- Se o roadmap e o código já existente (`proxxima_client.py` ou outro) divergirem em algum ponto, pare e pergunte em vez de assumir qual dos dois está certo.
- Mudança de escopo (adicionar fonte de dado nova, dar ao agente qualquer capacidade de escrita/ação) sempre exige confirmação explícita — não é uma extensão "óbvia" a ser feita sem perguntar.
