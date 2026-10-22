import { predict, predictStatus } from "@/lib/server/hotelml-api"

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
