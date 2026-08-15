A concepção

Você é coordenador de operações numa unidade de telecom, com ~35 técnicos e dois núcleos (Campina Grande e Lagoa Seca). No dia a dia, tomar decisão exige cruzar várias fontes — recorrência, produtividade, pontuação de inspeção, férias, banco de horas, solicitações em aberto — abrindo tela por tela, cruzando na cabeça ou no Excel. Você já tinha o OpenCode com credenciais do Gemini disponíveis e queria transformar isso num agente que consulta e cruza essas fontes por você, sem tomar decisão sozinho — puramente consultivo, pelo menos nessa fase.

A primeira arquitetura

Desenhamos um modelo em camadas: fontes de dados → API própria de agregação (FastAPI + Postgres) → tools expostas ao Gemini via function calling → agente (OpenCode) → você. A lógica: não jogar dado bruto no LLM, e sim dar a ele ferramentas que já retornam informação cruzada e calculada, porque LLM erra em aritmética e em juntar múltiplas fontes de forma confiável — o cruzamento pesado fica no backend, o agente só orquestra e explica.

O primeiro roadmap (v1) tinha 8 sprints, todos assumindo que a maior parte do dado viria de planilhas/Excel tratadas manualmente.

O ponto de virada: "isso vale a pena?"

Antes de investir semanas nisso, você fez a pergunta certa: com dado vindo de planilha, PDF e API ao mesmo tempo, será que o esforço de tratamento não ia superar o ganho? A resposta que chegamos: o agente em si é a parte barata do projeto — o custo real está sempre em tratar dado heterogêneo até virar algo confiável, com ou sem IA. A saída foi não tentar automatizar tudo de uma vez: separar por esforço de integração (API pronta → automatiza já; planilha que você já mantém → automatiza fácil; PDF → mantém manual, só convertendo pra csv/xlsx, que você já sabia fazer) e reconhecer que "detectar padrão fora do normal" não é mágica do LLM — precisa de regra explícita definida por você, o agente só executa e explica.

A investigação que mudou tudo

Isso foi a parte mais valiosa da conversa. Em vez de assumir que teria que construir integrações do zero, fomos investigando, via DevTools do navegador, o que os painéis que você já usa realmente consultam por trás. Isso revelou:

painel-ope.vercel.app — banco de horas, HE e infrações, com rankings já calculados. Autenticação por cookie de sessão válido ~7 dias.
aniel-aovivo (webhook n8n) — resumo agregado de solicitações, sem autenticação nenhuma.
Excel de recorrência — export manual (quase diário), com a cadeia de recorrência já calculada por protocolo, mas sem atribuição de técnico.
Painel_ServicosApi/GetAll (Proxxima Connect) — a API real por trás de tudo, com login ASP.NET clássico (token anti-forgery + cookies). E aí veio a virada final: você já tinha construído e testado um client Python pra isso (proxxima_client.py), rodando num app local seu. Isso resolveu de uma vez o maior risco técnico do projeto (autenticação) e ainda destravou o join que faltava — usar o campo tecnico do GetAll pra enriquecer o Excel de recorrência via número de protocolo.
A arquitetura final (v3)

Quatro fontes reais, cada uma com seu grau de automação:

Fonte	Cobre	Automação
ProxximaClient (portado)	Solicitações + técnico por OS	Total, já testado
painel-ope	Banco de horas, HE, infrações	Total, com renovação de cookie a cada ~7 dias
Excel de recorrência	Recorrência (enriquecida via join)	Download manual, ingestão automática
Google Sheets	Inspeção	100% manual, baixo volume

Roadmap de 8 sprints (~6-7 semanas), do schema de dados até relatório automático e robustez de produção — bem menor em risco do que a v1, porque a parte mais incerta (autenticação) já está resolvida.

Como isso vai funcionar no uso real, quando pronto

No dia a dia, depois de tudo implantado: jobs rodam sozinhos em background sincronizando as fontes pro Postgres (Proxxima a cada ~30 min, painel-ope diariamente). Você abre o OpenCode e pergunta em linguagem natural — "quem em Campina Grande está com recorrência alta essa semana?", "status geral das duas unidades agora", "gera o relatório da semana pra reunião de segunda". O agente decide quais tools chamar, elas batem no seu backend (que já tem tudo cruzado e calculado), e ele te devolve a resposta ou gera o .docx pronto. Você continua sendo quem decide — o agente só elimina o trabalho de abrir tela por tela e cruzar na mão antes de decidir.

Os únicos pontos de manutenção humana que sobram: renovar o cookie do painel-ope a cada semana (alerta automático avisa), baixar o Excel de recorrência periodicamente (você já faz isso), e alimentar a aba de Inspeção manualmente (baixo volume, 35 técnicos).