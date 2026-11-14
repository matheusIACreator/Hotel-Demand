import { predict, predictStatus } from "@/lib/server/hotelml-api"

// Limite da função na Vercel, em segundos: cobre PREDICT_TIMEOUT_MS com margem para responder.
export const maxDuration = 60

export async function POST(request: Request) {
  const body = await request.json().catch(() => null)
  const result = await predict(
    (body as { booking?: unknown } | null)?.booking ?? null
  )
  return Response.json(result, {
    status: predictStatus(result),
    headers: { "Cache-Control": "no-store" },
  })
}
