"use client"

import { useEffect, useState } from "react"
import { RotateCw } from "lucide-react"

import { StatusDot } from "@/components/status-dot"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useApiHealth, type HealthView } from "@/hooks/use-api-health"
import { formatTime } from "@/lib/format"

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.round((now - since) / 1_000))
  return <span className="tabular-nums">{seconds} s</span>
}

export function ApiStatusView({
  view,
  onRetry,
}: {
  view: HealthView
  onRetry: () => void
}) {
  return (
    <div
      className="surface p-5"
      aria-live="polite"
      aria-busy={view.status === "checking"}
    >
      {view.status === "checking" ? (
        <div className="space-y-3">
          <p className="flex items-center gap-2 text-sm font-medium">
            <StatusDot tone="neutral" />
            Verificando o serviço…
          </p>
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
      ) : null}

      {view.status === "starting" ? (
        <div className="space-y-2">
          <p className="flex items-center gap-2 text-sm font-medium">
            <StatusDot tone="warning" pulse />
            Iniciando o serviço…
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            A API escala para zero réplicas quando fica sem uso, então o
            primeiro acesso depois de uma pausa demora mais. Aguardando há{" "}
            <Elapsed since={view.since} />.
          </p>
        </div>
      ) : null}

      {view.status === "ready" ? (
        <div className="space-y-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            <StatusDot tone="success" />
            Serviço pronto
          </p>
          <dl className="grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Modelo carregado</dt>
              <dd className="font-medium break-all">{view.result.modelName}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Versão</dt>
              <dd className="font-medium tabular-nums">
                {view.result.modelVersion}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Verificado às</dt>
              <dd className="font-medium tabular-nums">
                {formatTime(view.result.checkedAt)}
              </dd>
            </div>
          </dl>
          <p className="text-xs text-muted-foreground">
            Esta verificação levou{" "}
            <span className="tabular-nums">{view.result.latencyMs} ms</span>{" "}
            entre o servidor da interface e a API. É uma medição única, não uma
            latência agregada.
          </p>
        </div>
      ) : null}

      {view.status === "unavailable" ? (
        <div className="space-y-3">
          <p className="flex items-center gap-2 text-sm font-medium">
            <StatusDot tone="danger" />
            Serviço indisponível
          </p>
          <p className="text-sm text-muted-foreground">{view.detail}</p>
          <Button variant="outline" onClick={onRetry}>
            <RotateCw data-icon="inline-start" />
            Tentar novamente
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export function ApiStatus() {
  const { view, retry } = useApiHealth()
  return <ApiStatusView view={view} onRetry={() => void retry()} />
}
