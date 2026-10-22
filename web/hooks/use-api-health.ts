"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import type { HealthResult } from "@/lib/api-types"

// Intervalos entre verificações enquanto a réplica arranca; o último repete-se.
const RETRY_DELAYS_MS = [2_000, 3_000, 5_000, 8_000]
// Acima do limite da startup probe da Container App (30 falhas × 5 s).
export const MAX_WAIT_MS = 180_000

export type HealthView =
  | { status: "checking" }
  | { status: "starting"; since: number; detail: string }
  | { status: "ready"; result: Extract<HealthResult, { state: "ready" }> }
  | { status: "unavailable"; detail: string }

export async function fetchHealth(): Promise<HealthResult> {
  const response = await fetch("/api/health", { cache: "no-store" })
  return (await response.json()) as HealthResult
}

/**
 * Consulta /api/health até a API ficar pronta e depois para: verificações periódicas manteriam a
 * réplica acordada e custariam dinheiro sem trazer informação nova.
 */
export function useApiHealth() {
  const [view, setView] = useState<HealthView>({ status: "checking" })
  const run = useRef(0)

  const check = useCallback(async () => {
    const id = ++run.current
    const since = Date.now()
    let attempt = 0
    setView({ status: "checking" })

    while (run.current === id) {
      let result: HealthResult
      try {
        result = await fetchHealth()
      } catch {
        result = {
          state: "starting",
          checkedAt: new Date().toISOString(),
          detail: "Sem resposta do servidor da interface.",
        }
      }
      if (run.current !== id) return

      if (result.state === "ready") {
        setView({ status: "ready", result })
        return
      }
      if (result.state === "error") {
        setView({ status: "unavailable", detail: result.detail })
        return
      }
      if (Date.now() - since > MAX_WAIT_MS) {
        setView({
          status: "unavailable",
          detail: "O serviço não ficou pronto dentro do tempo esperado.",
        })
        return
      }
      setView({ status: "starting", since, detail: result.detail })
      const delay =
        RETRY_DELAYS_MS[Math.min(attempt++, RETRY_DELAYS_MS.length - 1)]
      await new Promise((resolve) => setTimeout(resolve, delay))
    }
  }, [])

  useEffect(() => {
    const runs = run
    // A verificação é assíncrona; o estado só muda depois de cada resposta.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void check()
    // Invalida o ciclo em curso ao desmontar, para não atualizar estado de um componente morto.
    return () => {
      runs.current++
    }
  }, [check])

  return { view, retry: check }
}
