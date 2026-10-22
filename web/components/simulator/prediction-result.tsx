"use client"

import { AlertCircle, RotateCw } from "lucide-react"

import { StatusDot } from "@/components/status-dot"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import type { PredictFailure } from "@/lib/api-types"
import { FIELD_LABELS } from "@/lib/contract/fields"
import { formatPercent, formatTime } from "@/lib/format"
import {
  changedFields,
  deltaPoints,
  formatPoints,
  type Simulation,
} from "@/lib/simulation"
import { cn } from "@/lib/utils"

export type RunPhase =
  | { phase: "idle" }
  | { phase: "sending" }
  | { phase: "waking"; since: number }
  | { phase: "error"; failure: PredictFailure }

export function ProbabilityBar({
  probability,
  threshold,
  tone,
}: {
  probability: number
  threshold: number
  tone: "success" | "warning"
}) {
  return (
    <div className="space-y-1.5" aria-hidden>
      <div className="relative h-3 rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 ease-out",
            tone === "warning" ? "bg-warning" : "bg-success"
          )}
          style={{ width: `${probability * 100}%` }}
        />
        <div
          className="absolute -top-1 -bottom-1 w-px bg-foreground/60"
          style={{ left: `${threshold * 100}%` }}
        />
      </div>
      <div className="relative h-4 text-xs text-muted-foreground">
        <span className="absolute left-0">0%</span>
        <span
          className="absolute -translate-x-1/2"
          style={{ left: `${threshold * 100}%` }}
        >
          limiar {threshold.toLocaleString("pt-BR")}
        </span>
        <span className="absolute right-0">100%</span>
      </div>
    </div>
  )
}

function ResultBody({
  current,
  previous,
}: {
  current: Simulation
  previous?: Simulation
}) {
  const { result } = current
  const tone = result.isCanceled ? "warning" : "success"
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="text-sm text-muted-foreground">
          Probabilidade estimada de cancelamento
        </p>
        <p className="font-heading text-5xl tracking-tight tabular-nums">
          {formatPercent(result.probability)}
        </p>
      </div>

      <ProbabilityBar
        probability={result.probability}
        threshold={result.threshold}
        tone={tone}
      />

      <div
        className={cn(
          "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm",
          tone === "warning"
            ? "border-warning/30 bg-warning/5"
            : "border-success/30 bg-success/5"
        )}
      >
        <span className="mt-1.5">
          <StatusDot tone={tone} />
        </span>
        <p>
          <span
            className={cn(
              "font-medium",
              tone === "warning" ? "text-warning" : "text-success"
            )}
          >
            {result.isCanceled
              ? "Cancelamento provável"
              : "Manutenção provável"}
          </span>
          <span className="text-muted-foreground">
            {" "}
            · decisão da API com limiar fixo de{" "}
            {result.threshold.toLocaleString("pt-BR")} (cancela quando p ≥{" "}
            {result.threshold.toLocaleString("pt-BR")}).
          </span>
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Modelo</dt>
          <dd className="font-medium break-all">{result.modelName}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Versão</dt>
          <dd className="font-medium tabular-nums">{result.modelVersion}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Calculado às</dt>
          <dd className="font-medium tabular-nums">
            {formatTime(result.receivedAt)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Tempo de resposta</dt>
          <dd className="font-medium tabular-nums">{result.latencyMs} ms</dd>
        </div>
      </dl>

      {previous ? <Comparison previous={previous} current={current} /> : null}

      <p className="text-xs leading-relaxed text-muted-foreground">
        É uma estimativa estatística, não uma certeza. A API ainda não fornece
        explicações por fator para cada previsão.
      </p>
    </div>
  )
}

function Comparison({
  previous,
  current,
}: {
  previous: Simulation
  current: Simulation
}) {
  const { result } = current
  const changed = changedFields(previous.booking, current.booking)
  return (
    <div className="space-y-2 border-t pt-4 text-sm">
      <p className="font-medium">Comparação com a previsão anterior</p>
      <p className="text-muted-foreground">
        <span className="tabular-nums">
          {formatPercent(previous.result.probability)}
        </span>{" "}
        →{" "}
        <span className="text-foreground tabular-nums">
          {formatPercent(result.probability)}
        </span>{" "}
        (
        {formatPoints(
          deltaPoints(previous.result.probability, result.probability)
        )}
        )
        {previous.result.modelVersion !== result.modelVersion
          ? ` · versões diferentes do modelo (${previous.result.modelVersion} → ${result.modelVersion})`
          : null}
      </p>
      <p className="text-muted-foreground">
        {changed.length === 0
          ? "Mesmos dados da previsão anterior."
          : `Campos alterados: ${changed
              .map((name) => FIELD_LABELS[name])
              .join(", ")}.`}
      </p>
    </div>
  )
}

export function PredictionPanel({
  run,
  current,
  previous,
  onRetry,
}: {
  run: RunPhase
  current?: Simulation
  previous?: Simulation
  onRetry: () => void
}) {
  const busy = run.phase === "sending" || run.phase === "waking"

  return (
    <section
      aria-labelledby="resultado-titulo"
      className="min-h-[26rem] surface p-5 sm:p-6"
    >
      <h2 id="resultado-titulo" className="mb-5 font-heading text-xl">
        Resultado
      </h2>

      <div aria-live="polite" aria-busy={busy} className="space-y-4">
        {run.phase === "waking" ? (
          <p className="flex items-center gap-2 text-sm font-medium">
            <StatusDot tone="warning" pulse />
            Iniciando o serviço… a primeira previsão depois de uma pausa demora
            mais.
          </p>
        ) : null}
        {run.phase === "sending" ? (
          <p className="text-sm text-muted-foreground">
            Calculando a estimativa…
          </p>
        ) : null}

        {run.phase === "error" ? (
          <div
            role="alert"
            className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm"
          >
            <p className="flex items-center gap-2 font-medium text-destructive">
              <AlertCircle className="size-4" aria-hidden />
              {run.failure.message}
            </p>
            {run.failure.issues?.some((i) => !i.field) ? (
              <ul className="ml-6 list-disc text-muted-foreground">
                {run.failure.issues
                  .filter((i) => !i.field)
                  .map((i) => (
                    <li key={i.message}>{i.message}</li>
                  ))}
              </ul>
            ) : null}
            {run.failure.kind === "validation" ? (
              <p className="text-muted-foreground">
                Revise os campos destacados no formulário.
              </p>
            ) : (
              <Button variant="outline" onClick={onRetry}>
                <RotateCw data-icon="inline-start" />
                Tentar novamente
              </Button>
            )}
          </div>
        ) : null}

        {current ? (
          <div
            className={cn(
              "animate-result-in transition-opacity duration-150",
              busy && "opacity-50"
            )}
            key={current.result.receivedAt}
          >
            <ResultBody current={current} previous={previous} />
          </div>
        ) : busy ? (
          <div className="space-y-5" aria-hidden>
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-12 w-32" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : run.phase !== "error" ? (
          <p className="text-sm leading-relaxed text-muted-foreground">
            Carregue o exemplo ou preencha a reserva e clique em{" "}
            <span className="font-medium text-foreground">
              Estimar cancelamento
            </span>
            . O resultado aparece aqui, com a versão do modelo usada.
          </p>
        ) : null}
      </div>
    </section>
  )
}
