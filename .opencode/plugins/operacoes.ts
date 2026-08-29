// Plugin do agente operacoes — formato oficial @opencode-ai/plugin.
// O pacote esta instalado localmente em .opencode/node_modules, o que faz o
// auto-installer do opencode pular o reify (que falharia na versao "local").

import { tool } from "@opencode-ai/plugin"
import { z } from "zod"
import { readFileSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"

let API_BASE = process.env.OPS_API_URL ?? "http://localhost:8100"
let API_TOKEN = process.env.OPS_API_TOKEN ?? ""

const RAIZ_DO_PROJETO = dirname(dirname(dirname(fileURLToPath(import.meta.url))))

async function lerEnvArquivo(caminho: string): Promise<Record<string, string>> {
  const vars: Record<string, string> = {}
  try {
    const conteudo = readFileSync(caminho, "utf-8")
    for (const linha of conteudo.split(/\r?\n/)) {
      const semComentario = linha.trim().replace(/^export\s+/, "")
      if (!semComentario || semComentario.startsWith("#")) continue
      const idx = semComentario.indexOf("=")
      if (idx <= 0) continue
      const chave = semComentario.slice(0, idx).trim()
      let valor = semComentario.slice(idx + 1).trim()
      if (valor.startsWith('"') && valor.endsWith('"')) valor = valor.slice(1, -1)
      else if (valor.startsWith("'") && valor.endsWith("'")) valor = valor.slice(1, -1)
      vars[chave] = valor
    }
  } catch {
    // sem .env disponível — segue só com o que veio de process.env
  }
  return vars
}

export const OperacoesPlugin = async (input: { directory?: string }) => {
  const directory = input.directory ?? ""
  if (!API_TOKEN || API_BASE === process.env.OPS_API_URL) {
    const candidatos = [
      join(RAIZ_DO_PROJETO, ".env"),
      join(directory, ".env"),
      join(process.cwd(), ".env"),
    ]
    let envDoProjeto: Record<string, string> = {}
    for (const caminho of candidatos) {
      envDoProjeto = await lerEnvArquivo(caminho)
      if (envDoProjeto["OPS_API_TOKEN"]) break
    }
    if (!API_TOKEN) {
      API_TOKEN = envDoProjeto["OPS_API_TOKEN"] ?? ""
    }
    if (!process.env.OPS_API_URL) {
      API_BASE = envDoProjeto["OPS_API_URL"] ?? API_BASE
    }
  }

  async function chamarApi(path: string) {
    const headers: Record<string, string> = {}
    if (API_TOKEN) {
      headers.Authorization = `Bearer ${API_TOKEN}`
    }
    const res = await fetch(`${API_BASE}${path}`, { headers })
    if (!res.ok) {
      throw new Error(`API respondeu ${res.status} em ${path}`)
    }
    const dados = await res.json()
    return JSON.stringify(dados, null, 2)
  }

  function semanaAtual(): { de: string; ate: string } {
    const hoje = new Date()
    const dia = (hoje.getDay() + 6) % 7
    const segunda = new Date(hoje)
    segunda.setDate(hoje.getDate() - dia)
    const domingo = new Date(segunda)
    domingo.setDate(segunda.getDate() + 6)
    const fmt = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    return { de: fmt(segunda), ate: fmt(domingo) }
  }

  const periodoDe = z.string().describe("Início do período (YYYY-MM-DD). Se omitido, usa a semana atual.")
  const periodoAte = z.string().describe("Fim do período (YYYY-MM-DD). Se omitido, usa a semana atual.")

  return {
    tool: {
      getDiagnosticoTecnico: tool({
        description:
          "Diagnóstico completo de um técnico cruzando as 3 fontes: recorrência, produtividade, HE, infrações e última inspeção, com alertas. Use quando a pergunta for sobre um técnico específico. VALIDAÇÃO: recorrencia_reaberturas = OS do técnico que são recorrência (é_recorrencia=SIM) no período; recorrencia_os_no_analitico = todas as OS do técnico listadas no analítico (inclui não-recorrentes) — para saber quantas recorrências o técnico tem, use recorrencia_reaberturas.",
        args: {
          nome_tecnico: z
            .string()
            .describe("Nome completo do técnico em MAIÚSCULAS (ex.: ALVARO CORREIA DE SOUSA NETO)"),
          periodo_de: periodoDe.optional(),
          periodo_ate: periodoAte.optional(),
        },
        async execute(args: {
          nome_tecnico: string
          periodo_de?: string
          periodo_ate?: string
        }) {
          const { de, ate } = semanaAtual()
          const params = new URLSearchParams({
            periodo_de: args.periodo_de ?? de,
            periodo_ate: args.periodo_ate ?? ate,
          })
          return chamarApi(
            `/diagnostico/tecnico/${encodeURIComponent(args.nome_tecnico)}?${params}`,
          )
        },
      }),
      getStatusUnidade: tool({
        description:
          "Status agregado de uma unidade: backlog (abertas), fechadas produtivas/improdutivas, canceladas, HE e recorrências. Use para perguntas do tipo 'como está Campina Grande / Lagoa Seca'.",
        args: {
          unidade: z
            .string()
            .describe("Unidade: CAMPINA GRANDE ou LAGOA SECA"),
          periodo_de: periodoDe.optional(),
          periodo_ate: periodoAte.optional(),
        },
        async execute(args: {
          unidade: string
          periodo_de?: string
          periodo_ate?: string
        }) {
          const { de, ate } = semanaAtual()
          const params = new URLSearchParams({
            periodo_de: args.periodo_de ?? de,
            periodo_ate: args.periodo_ate ?? ate,
          })
          return chamarApi(
            `/diagnostico/status-unidade/${encodeURIComponent(args.unidade)}?${params}`,
          )
        },
      }),
      getPlanilha: tool({
        description:
          "Lê dados da planilha Google Sheets. Primeiro chame sem aba para ver a lista de abas disponíveis. Depois chame com o nome da aba para ler os dados. Limite padrão: 200 linhas.",
        args: {
          aba: z
            .string()
            .describe(
              "Nome da aba da planilha. Se omitido, retorna a lista de abas disponíveis.",
            ),
          limite: z
            .number()
            .describe("Máximo de linhas retornadas (padrão: 200, máx: 2000)")
            .optional(),
        },
        async execute(args: { aba?: string; limite?: number }) {
          if (!args.aba) {
            return chamarApi("/planilha/abas")
          }
          const params = new URLSearchParams()
          if (args.limite) params.set("limite", String(args.limite))
          const qs = params.toString() ? `?${params}` : ""
          return chamarApi(
            `/planilha/${encodeURIComponent(args.aba)}${qs}`,
          )
        },
      }),
      getRelatorioSemanal: tool({
        description:
          "Gera um relatório semanal em .docx para uma unidade. Retorna o ID e a URL de download do relatório. Use quando o usuário pedir para gerar um relatório.",
        args: {
          unidade: z
            .string()
            .describe("Unidade: CAMPINA GRANDE ou LAGOA SECA"),
          periodo_de: periodoDe.optional(),
          periodo_ate: periodoAte.optional(),
        },
        async execute(args: {
          unidade: string
          periodo_de?: string
          periodo_ate?: string
        }) {
          const { de, ate } = semanaAtual()
          const headers: Record<string, string> = { "Content-Type": "application/json" }
          if (API_TOKEN) headers.Authorization = `Bearer ${API_TOKEN}`
          const res = await fetch(`${API_BASE}/relatorios`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              unidade: args.unidade,
              periodo_de: args.periodo_de ?? de,
              periodo_ate: args.periodo_ate ?? ate,
            }),
          })
          if (!res.ok) throw new Error(`API respondeu ${res.status}`)
          const dados = await res.json()
          return JSON.stringify({
            ...dados,
            download_url: `${API_BASE}/relatorios/${dados.id}/download`,
          }, null, 2)
        },
      }),
      getTempoReal: tool({
        description:
          "Dados em TEMPO REAL direto da API Proxxima (sem usar o banco). Use para panorama do dia, situação atual de uma unidade, ou quando precisar de dados frescos/atualizados. Retorna: abertas agora (por status), encerradas ontem, encerradas hoje (com quebra por natureza e produtiva/improdutiva), abertas hoje (por natureza), SLA vencido e sem técnico.",
        args: {
          unidade: z
            .string()
            .describe("Unidade: CAMPINA GRANDE ou LAGOA SECA"),
        },
        async execute(args: { unidade: string }) {
          return chamarApi(
            `/diagnostico/tempo-real/${encodeURIComponent(args.unidade)}`,
          )
        },
      }),
    },
  }
}
