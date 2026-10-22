import type { Metadata } from "next"
import Link from "next/link"
import { ArrowRight, ExternalLink } from "lucide-react"

import { SplitTimeline } from "@/components/model/split-timeline"
import { VersionCheck } from "@/components/model/version-check"
import { OperationalIndicators } from "@/components/operational-indicators"
import { PageHeader, Section } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  formatDate,
  formatInteger,
  formatMetric,
  formatPercent,
} from "@/lib/format"
import { DOCS } from "@/lib/links"
import {
  ESTIMATORS,
  METRIC_INFO,
  MODEL_CARD,
  type MetricKey,
} from "@/lib/model-card"

export const metadata: Metadata = { title: "Modelo" }

const { source, dataset, metrics } = MODEL_CARD

const DECISIONS = [
  {
    title: "Sem vazamento de informação",
    text: "reservation_status, reservation_status_date e assigned_room_type foram excluídas: só existem depois do desfecho ou do check-in.",
    href: DOCS.adrDataset,
    adr: "ADR 0001",
  },
  {
    title: "Divisão temporal",
    text: "Treino no passado e teste no futuro, como na operação real. As métricas tendem a ser mais conservadoras que numa divisão aleatória.",
    href: DOCS.adrDataset,
    adr: "ADR 0001",
  },
  {
    title: "Features dentro do pipeline",
    text: "O modelo registrado aceita o payload cru da API, então treino, API e lote calculam as features da mesma forma.",
    href: DOCS.adrDataset,
    adr: "ADR 0001",
  },
  {
    title: "Promoção por aliases",
    text: "Cada treino vira challenger; só passa a champion se superar o atual em ROC AUC no mesmo conjunto de teste. Rollback troca aliases.",
    href: DOCS.adrRegistry,
    adr: "ADR 0002",
  },
  {
    title: "Snapshot imutável no serving",
    text: "A API carrega um bundle com versão explícita na inicialização; trocar aliases no registry não muda o modelo em execução.",
    href: DOCS.adrServing,
    adr: "ADR 0003",
  },
]

export default function Page() {
  return (
    <>
      <PageHeader
        title="Modelo"
        description="Como o modelo publicado foi treinado e avaliado: dataset, divisão temporal, métricas históricas e decisões de engenharia."
        action={
          <Button asChild variant="outline" size="lg" className="px-4">
            <Link href="/simular">
              Testar no simulador
              <ArrowRight data-icon="inline-end" />
            </Link>
          </Button>
        }
      />

      <div className="space-y-12">
        <Section
          title="Métricas históricas"
          description="Avaliação única no conjunto de teste temporal, registrada no treino. Não é medição de tráfego em produção."
        >
          <div className="space-y-5 surface p-5 sm:p-6">
            <dl className="grid gap-4 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-muted-foreground">Modelo</dt>
                <dd className="font-medium break-all">{source.model_name}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Versão</dt>
                <dd className="font-medium tabular-nums">
                  {source.model_version}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Treinado em</dt>
                <dd className="font-medium tabular-nums">
                  {formatDate(source.trained_at)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Run MLflow</dt>
                <dd className="font-mono text-xs break-all">{source.run_id}</dd>
              </div>
            </dl>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Métrica</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="hidden md:table-cell">
                    O que mede
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(Object.keys(METRIC_INFO) as MetricKey[]).map((key) => (
                  <TableRow key={key}>
                    <TableCell className="align-top">
                      <span className="font-medium">
                        {METRIC_INFO[key].label}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {METRIC_INFO[key].better} é melhor
                      </span>
                      <span className="block text-xs whitespace-normal text-muted-foreground md:hidden">
                        {METRIC_INFO[key].description}
                      </span>
                    </TableCell>
                    <TableCell className="text-right align-top font-medium tabular-nums">
                      {formatMetric(metrics[key])}
                    </TableCell>
                    <TableCell className="hidden align-top whitespace-normal text-muted-foreground md:table-cell">
                      {METRIC_INFO[key].description}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <p className="text-sm text-muted-foreground">
              Taxa de cancelamento no teste:{" "}
              <span className="text-foreground tabular-nums">
                {formatPercent(dataset.test_cancel_rate)}
              </span>{" "}
              (no treino:{" "}
              <span className="tabular-nums">
                {formatPercent(dataset.train_cancel_rate)}
              </span>
              ). É a referência da PR AUC para um classificador aleatório.
            </p>
            <p className="text-xs text-muted-foreground">
              Origem: métricas e parâmetros do run no MLflow e dataset local,
              exportados em {formatDate(source.exported_at)} por{" "}
              <code className="font-mono">scripts/export_model_card.py</code>.
            </p>
            <VersionCheck cardVersion={source.model_version} />
          </div>
        </Section>

        <Section
          title="Dados e divisão temporal"
          description="O modelo aprende com reservas passadas e é avaliado em reservas posteriores."
        >
          <div className="space-y-6 surface p-5 sm:p-6">
            <SplitTimeline
              trainStart={dataset.train_start}
              cutoff={dataset.test_cutoff}
              testEnd={dataset.test_end}
              trainRows={dataset.train_rows}
              testRows={dataset.test_rows}
            />
            <ul className="space-y-2 text-sm leading-relaxed text-muted-foreground">
              <li>
                Dataset{" "}
                <a
                  href={dataset.url}
                  className="inline-flex items-center gap-1 text-primary underline underline-offset-4"
                  target="_blank"
                  rel="noreferrer"
                >
                  {dataset.name}
                  <ExternalLink className="size-3" aria-hidden />
                  <span className="sr-only">(abre em nova aba)</span>
                </a>
                : {formatInteger(dataset.raw_rows)} reservas brutas;{" "}
                {formatInteger(dataset.removed_rows)} removidas na limpeza (zero
                hóspedes ou diária fora de 0 a 1000).
              </li>
              <li>
                O corte é feito por posição na ordem cronológica, por isso a
                data de corte ({formatDate(dataset.test_cutoff)}) aparece nos
                dois conjuntos.
              </li>
              <li>
                Estimador:{" "}
                {ESTIMATORS[MODEL_CARD.estimator] ?? MODEL_CARD.estimator}.
                Decisão com limiar fixo de 0,5 na API.
              </li>
              <li>
                A cópia do dataset no Hugging Face não declara licença; por isso
                os dados não são versionados no repositório.
              </li>
            </ul>
          </div>
        </Section>

        <Section title="Decisões de engenharia">
          <ul className="grid gap-4 sm:grid-cols-2">
            {DECISIONS.map((d) => (
              <li key={d.title} className="space-y-2 surface p-5">
                <h3 className="font-medium">{d.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {d.text}
                </p>
                <a
                  href={d.href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-primary underline underline-offset-4"
                >
                  {d.adr}
                  <ExternalLink className="size-3" aria-hidden />
                  <span className="sr-only">(abre em nova aba)</span>
                </a>
              </li>
            ))}
          </ul>
        </Section>

        <Section
          title="Indicadores operacionais"
          description="Separados das métricas históricas: descrevem o serviço em execução, não a avaliação do treino."
        >
          <OperationalIndicators />
        </Section>
      </div>
    </>
  )
}
