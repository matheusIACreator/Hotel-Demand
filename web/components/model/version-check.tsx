"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"

import { StatusDot } from "@/components/status-dot"
import { Button } from "@/components/ui/button"
import { waitForApi, type HealthView } from "@/hooks/use-api-health"

/**
 * Compara a versão das métricas com a versão carregada na API. Só consulta a API a pedido:
 * abrir esta página não deve acordar a réplica.
 */
export function VersionCheck({ cardVersion }: { cardVersion: string }) {
  const [view, setView] = useState<HealthView | null>(null)
  const busy = view?.status === "checking" || view?.status === "starting"

  async function check() {
    setView({ status: "checking" })
    await waitForApi(setView)
  }

  return (
    <div
      className="flex flex-wrap items-center gap-3 text-sm"
      aria-live="polite"
    >
      <Button variant="outline" onClick={() => void check()} disabled={busy}>
        {busy ? (
          <Loader2 className="animate-spin" data-icon="inline-start" />
        ) : null}
        Conferir versão carregada na API
      </Button>
      {view?.status === "starting" ? (
        <span className="flex items-center gap-2 text-muted-foreground">
          <StatusDot tone="warning" pulse />
          Iniciando o serviço…
        </span>
      ) : null}
      {view?.status === "ready" ? (
        view.result.modelVersion === cardVersion ? (
          <span className="flex items-center gap-2">
            <StatusDot tone="success" />A API carrega a versão{" "}
            {view.result.modelVersion}: estas métricas correspondem ao modelo em
            produção.
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <StatusDot tone="warning" />A API carrega a versão{" "}
            {view.result.modelVersion}; estas métricas são da versão{" "}
            {cardVersion} e não descrevem o modelo atual.
          </span>
        )
      ) : null}
      {view?.status === "unavailable" ? (
        <span className="flex items-center gap-2 text-muted-foreground">
          <StatusDot tone="danger" />
          Não foi possível conferir: {view.detail}
        </span>
      ) : null}
    </div>
  )
}
