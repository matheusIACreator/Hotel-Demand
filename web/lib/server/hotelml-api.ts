import type {
  FieldIssue,
  HealthResult,
  PredictFailure,
  PredictResult,
} from "@/lib/api-types"
import {
  DECISION_THRESHOLD,
  bookingSchema,
  predictResponseSchema,
  readyResponseSchema,
} from "@/lib/contract/booking"

// Curto o suficiente para o navegador voltar a perguntar; a réplica arranca em paralelo.
export const HEALTH_TIMEOUT_MS = 8_000
export const PREDICT_TIMEOUT_MS = 20_000

// Respostas do proxy da Azure enquanto não há réplica pronta, e o 503 do próprio /health/ready.
const STARTING_STATUSES = new Set([502, 503, 504])

class ConfigError extends Error {}

export function apiBaseUrl(): string {
  const url = process.env.HOTELML_API_URL?.trim()
  if (!url) throw new ConfigError("HOTELML_API_URL não está configurada.")
  return url.replace(/\/+$/, "")
}

function isTimeout(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    (error.name === "TimeoutError" || error.name === "AbortError")
  )
}

export async function checkHealth(): Promise<HealthResult> {
  const checkedAt = new Date().toISOString()
  let base: string
  try {
    base = apiBaseUrl()
  } catch (error) {
    return { state: "error", checkedAt, detail: (error as Error).message }
  }
  const start = performance.now()
  try {
    const response = await fetch(`${base}/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    })
    const latencyMs = Math.round(performance.now() - start)
    if (STARTING_STATUSES.has(response.status)) {
      return {
        state: "starting",
        checkedAt,
        detail: `A API respondeu ${response.status} enquanto inicia.`,
      }
    }
    if (!response.ok) {
      return {
        state: "error",
        checkedAt,
        detail: `A API respondeu ${response.status}.`,
      }
    }
    const parsed = readyResponseSchema.safeParse(await response.json())
    if (!parsed.success) {
      return {
        state: "error",
        checkedAt,
        detail: "Resposta de /health/ready fora do formato esperado.",
      }
    }
    return {
      state: "ready",
      modelName: parsed.data.model_name,
      modelVersion: parsed.data.model_version,
      checkedAt,
      latencyMs,
    }
  } catch (error) {
    if (isTimeout(error)) {
      return {
        state: "starting",
        checkedAt,
        detail:
          "A API ainda não respondeu; pode estar saindo de zero réplicas.",
      }
    }
    return {
      state: "starting",
      checkedAt,
      detail: "Não foi possível contatar a API.",
    }
  }
}

// Converte o `detail` de erro 422 da FastAPI em mensagens por campo.
function fastApiIssues(body: unknown): FieldIssue[] {
  const detail = (body as { detail?: unknown })?.detail
  if (!Array.isArray(detail)) return []
  return detail.map((item: { loc?: unknown[]; msg?: string }) => {
    const loc = Array.isArray(item.loc) ? item.loc : []
    const field = loc.length ? String(loc[loc.length - 1]) : null
    return { field, message: item.msg ?? "valor inválido" }
  })
}

function failure(
  kind: PredictFailure["kind"],
  message: string,
  issues?: FieldIssue[]
): PredictFailure {
  return { ok: false, kind, message, ...(issues ? { issues } : {}) }
}

export async function predict(input: unknown): Promise<PredictResult> {
  const parsed = bookingSchema.safeParse(input)
  if (!parsed.success) {
    return failure(
      "validation",
      "A reserva não respeita o contrato da API.",
      parsed.error.issues.map((issue) => ({
        field: issue.path.length ? String(issue.path[0]) : null,
        message: issue.message,
      }))
    )
  }

  let base: string
  try {
    base = apiBaseUrl()
  } catch (error) {
    return failure("config", (error as Error).message)
  }

  const start = performance.now()
  let response: Response
  try {
    response = await fetch(`${base}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bookings: [parsed.data] }),
      cache: "no-store",
      signal: AbortSignal.timeout(PREDICT_TIMEOUT_MS),
    })
  } catch (error) {
    return isTimeout(error)
      ? failure(
          "timeout",
          "A API demorou demais para responder. Tente novamente em instantes."
        )
      : failure("starting", "Não foi possível contatar a API.")
  }
  const latencyMs = Math.round(performance.now() - start)

  if (response.status === 422) {
    return failure(
      "validation",
      "A API recusou a reserva.",
      fastApiIssues(await response.json().catch(() => null))
    )
  }
  if (STARTING_STATUSES.has(response.status)) {
    return failure(
      "starting",
      "O serviço ainda está iniciando ou o modelo não está disponível."
    )
  }
  if (!response.ok) {
    return failure("upstream", `A API respondeu ${response.status}.`)
  }

  const body = predictResponseSchema.safeParse(
    await response.json().catch(() => null)
  )
  if (!body.success) {
    return failure("upstream", "Resposta de /predict fora do formato esperado.")
  }
  const [prediction] = body.data.predictions
  return {
    ok: true,
    modelName: body.data.model_name,
    modelVersion: body.data.model_version,
    probability: prediction.cancellation_probability,
    isCanceled: prediction.is_canceled,
    threshold: DECISION_THRESHOLD,
    latencyMs,
    receivedAt: new Date().toISOString(),
  }
}

export function predictStatus(result: PredictResult): number {
  if (result.ok) return 200
  return {
    validation: 422,
    starting: 503,
    timeout: 504,
    upstream: 502,
    config: 500,
  }[result.kind]
}
