import type { PredictSuccess } from "@/lib/api-types"
import type { Booking } from "@/lib/contract/booking"
import type { FieldName } from "@/lib/contract/fields"

export type Simulation = { booking: Booking; result: PredictSuccess }

export function changedFields(before: Booking, after: Booking): FieldName[] {
  return (Object.keys(after) as FieldName[]).filter(
    (name) => before[name] !== after[name]
  )
}

// Diferença em pontos percentuais entre duas probabilidades.
export function deltaPoints(before: number, after: number): number {
  return (after - before) * 100
}

export function formatPoints(delta: number): string {
  const rounded = Math.round(delta * 10) / 10
  if (rounded === 0) return "sem variação"
  const sign = rounded > 0 ? "+" : "−"
  return `${sign}${Math.abs(rounded).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} p.p.`
}
