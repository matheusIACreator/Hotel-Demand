"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import type { HealthResult } from "@/lib/api-types"

// Intervalos entre verificações enquanto a réplica arranca; o último repete-se.
const RETRY_DELAYS_MS = [2_000, 3_000, 5_000, 8_000]
// Acima do limite da startup probe da Container App (30 falhas × 5 s).
export const MAX_WAIT_MS = 180_000

export type ReadyHealth = Extract<HealthResult, { state: "ready" }>

export type HealthView =
  | { status: "checking" }
  | { status: "starting"; since: number; detail: string }
  | { status: "ready"; result: ReadyHealth }
  | { status: "unavailable"; detail: string }

async function fetchHealth(): Promise<HealthResult> {
  try {
    const response = await fetch("/api/health", { cache: "no-store" })
    return (await response.json()) as HealthResult
  } catch {
    return {
      state: "starting",
      checkedAt: new Date().toISOString(),
      detail: "Sem resposta do servidor da interface.",
    }
  }
}

/**
 * Consulta /api/health até a API ficar pronta e depois para: verificações periódicas manteriam a
 * réplica acordada e custariam dinheiro sem trazer informação nova.
 */
export async function waitForApi(
  onUpdate: (view: HealthView) => void,
  isCancelled: () => boolean = () => false
): Promise<HealthView> {
  const since = Date.now()
  for (let attempt = 0; ; attempt++) {
    const result = await fetchHealth()
    if (isCancelled()) return { status: "checking" }

    let view: HealthView
    if (result.state === "ready") {
      view = { status: "ready", result }
    } else if (result.state === "error") {
      view = { status: "unavailable", detail: result.detail }
    } else if (Date.now() - since > MAX_WAIT_MS) {
      view = {
        status: "unavailable",
        detail: "O serviço não ficou pronto dentro do tempo esperado.",
      }
    } else {
      onUpdate({ status: "starting", since, detail: result.detail })
      const delay =
        RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)]
      await new Promise((resolve) => setTimeout(resolve, delay))
      if (isCancelled()) return { status: "checking" }
      continue
    }
    onUpdate(view)
    return view
  }
}

export function useApiHealth() {
  const [view, setView] = useState<HealthView>({ status: "checking" })
  const run = useRef(0)

  const check = useCallback(async () => {
    const id = ++run.current
    setView({ status: "checking" })
    return waitForApi(setView, () => run.current !== id)
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
