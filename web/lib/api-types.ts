// Respostas das rotas /api/* do Next.js, partilhadas entre servidor e navegador.

export type HealthResult =
  | {
      state: "ready"
      modelName: string
      modelVersion: string
      checkedAt: string
      latencyMs: number
    }
  // Sem resposta a tempo ou erro do proxy da Azure: típico enquanto a réplica arranca do zero.
  | { state: "starting"; checkedAt: string; detail: string }
  | { state: "error"; checkedAt: string; detail: string }

export type PredictSuccess = {
  ok: true
  modelName: string
  modelVersion: string
  probability: number
  isCanceled: boolean
  threshold: number
  latencyMs: number
  receivedAt: string
}

export type FieldIssue = { field: string | null; message: string }

export type PredictFailure = {
  ok: false
  kind: "validation" | "starting" | "timeout" | "upstream" | "config"
  message: string
  issues?: FieldIssue[]
}

export type PredictResult = PredictSuccess | PredictFailure
