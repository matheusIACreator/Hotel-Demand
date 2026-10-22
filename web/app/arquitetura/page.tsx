import type { Metadata } from "next"

import { DocLink, StepList } from "@/components/doc-link"
import { PageHeader, Section } from "@/components/page-header"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { DOCS } from "@/lib/links"

export const metadata: Metadata = { title: "Arquitetura e operação" }

const FLOW = [
  {
    title: "Dataset",
    detail: "gemuchu/hotel_bookings, baixado em tempo de execução",
  },
  { title: "Treino", detail: "validação, limpeza, divisão temporal, pipeline" },
  {
    title: "Registry MLflow",
    detail: "challenger, champion, previous_champion",
  },
  { title: "Bundle", detail: "hotelml export: versão explícita + manifest" },
  { title: "Imagem", detail: "Docker no ACR, referenciada por digest" },
  { title: "Container Apps", detail: "FastAPI, 0 a 1 réplica" },
  { title: "Esta interface", detail: "rotas de servidor Next.js" },
]

const AZURE = [
  ["Resource group", "Agrupa os recursos; metadados em West Europe"],
  ["Container Registry (Basic)", "Guarda as imagens da API"],
  ["Log Analytics (PerGB2018)", "Logs do ambiente, retenção de 30 dias"],
  ["Container Apps Environment", "Perfil Consumption, em North Europe"],
  ["Identidade gerida", "Apenas AcrPull, para a API puxar a imagem"],
  [
    "Container App",
    "0,5 vCPU, 1 GiB, 0–1 réplicas, probes de startup, liveness e readiness",
  ],
  ["Orçamento", "Alertas a 50%, 80% e 100%; não interrompe os recursos"],
]

export default function Page() {
  return (
    <>
      <PageHeader
        title="Arquitetura e operação"
        description="Do treino ao serving: registry com aliases, snapshot imutável, imagem por digest no ACR, Container Apps e CI/CD."
      />

      <div className="space-y-12">
        <Section
          title="Fluxo dos dados e do modelo"
          description="Cada etapa entrega um artefato identificado à seguinte."
        >
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {FLOW.map((step, i) => (
              <li key={step.title} className="relative space-y-1 surface p-4">
                <span className="text-xs text-muted-foreground tabular-nums">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <p className="font-medium">{step.title}</p>
                <p className="text-sm text-muted-foreground">{step.detail}</p>
              </li>
            ))}
          </ol>
          <p className="text-sm leading-relaxed text-muted-foreground">
            O navegador nunca fala com a Azure diretamente: as rotas{" "}
            <code className="font-mono text-xs">/api/health</code> e{" "}
            <code className="font-mono text-xs">/api/predict</code> desta
            interface chamam a API no servidor, com timeout e tratamento do cold
            start (inicialização a frio).
          </p>
        </Section>

        <Section
          title="Serviços Azure"
          description="Definidos em Terraform. A API foi publicada e validada em 22/10/2026."
        >
          <div className="surface p-2 sm:p-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Recurso</TableHead>
                  <TableHead>Função</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {AZURE.map(([name, role]) => (
                  <TableRow key={name}>
                    <TableCell className="align-top font-medium whitespace-normal">
                      {name}
                    </TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">
                      {role}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            O ingress é público para demonstração, sem autenticação de clientes.
            Não envie dados pessoais para este endpoint.
          </p>
        </Section>

        <Section title="CI/CD">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-3 surface p-5 sm:p-6">
              <h3 className="font-medium">CI em cada pull request</h3>
              <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted-foreground">
                <li>
                  Ruff, formatação, mypy e pytest com cobertura mínima de 80%
                </li>
                <li>
                  Treino sintético, exportação do bundle e smoke test do
                  container
                </li>
                <li>Testes de integração Spark num container com Java</li>
                <li>Terraform fmt e validate</li>
                <li>Frontend: lint, formatação, tipos, testes e build</li>
              </ul>
              <DocLink href={DOCS.ciWorkflow} className="text-sm">
                ci.yml
              </DocLink>
            </div>
            <div className="space-y-3 surface p-5 sm:p-6">
              <h3 className="font-medium">Deploy manual</h3>
              <StepList
                steps={[
                  {
                    title: "CI obrigatório",
                    text: "Reutiliza o workflow de CI.",
                  },
                  {
                    title: "Login por OIDC",
                    text: "Sem password do ACR nem client secret no GitHub.",
                  },
                  {
                    title: "Exporta o champion",
                    text: "A partir de um MLflow remoto acessível ao runner.",
                  },
                  {
                    title: "Publica por digest",
                    text: "Smoke test da imagem, push para o ACR e nova revisão validada.",
                  },
                ]}
              />
              <p className="text-sm text-muted-foreground">
                Configuração pendente: identidade OIDC, variáveis do GitHub e um
                registry MLflow remoto. O deploy atual foi feito localmente.
              </p>
              <DocLink href={DOCS.deployWorkflow} className="text-sm">
                deploy.yml
              </DocLink>
            </div>
          </div>
        </Section>

        <Section title="Operação">
          <ul className="grid gap-4 sm:grid-cols-2">
            <li className="space-y-2 surface p-5">
              <h3 className="font-medium">Inicialização a frio</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Com zero réplicas em repouso, o primeiro pedido depois de uma
                pausa espera o container iniciar e carregar o modelo. A
                readiness só passa depois de o modelo carregar.
              </p>
            </li>
            <li className="space-y-2 surface p-5">
              <h3 className="font-medium">Rollback</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Trocar aliases no registry não muda a API em execução: é preciso
                publicar outro snapshot ou voltar a uma revisão anterior.
              </p>
              <DocLink href={DOCS.runbookRollback} className="text-sm">
                Runbook de rollback
              </DocLink>
            </li>
          </ul>
        </Section>

        <Section title="Documentação">
          <ul className="grid gap-3 surface p-5 text-sm sm:grid-cols-2 sm:p-6">
            <li>
              <DocLink href={DOCS.readme}>README do projeto</DocLink>
            </li>
            <li>
              <DocLink href={DOCS.runbookDeploy}>
                Runbook de deploy Azure
              </DocLink>
            </li>
            <li>
              <DocLink href={DOCS.adrServing}>
                ADR 0003: serving e deploy
              </DocLink>
            </li>
            <li>
              <DocLink href={DOCS.adrRegistry}>
                ADR 0002: registry por aliases
              </DocLink>
            </li>
            <li>
              <DocLink href={DOCS.terraform}>Terraform (infra/main.tf)</DocLink>
            </li>
            <li>
              <DocLink href={DOCS.runbookPipelines}>
                Runbook de pipelines
              </DocLink>
            </li>
          </ul>
        </Section>
      </div>
    </>
  )
}
