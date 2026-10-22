import { checkHealth } from "@/lib/server/hotelml-api"

export const dynamic = "force-dynamic"

export async function GET() {
  const result = await checkHealth()
  return Response.json(result, {
    headers: { "Cache-Control": "no-store" },
  })
}
