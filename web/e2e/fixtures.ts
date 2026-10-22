import type { Page } from "@playwright/test"

export const READY = {
  state: "ready",
  modelName: "hotel-cancellation",
  modelVersion: "1",
  checkedAt: "2026-10-22T10:00:00.000Z",
  latencyMs: 90,
}

export const prediction = (probability: number) => ({
  ok: true,
  modelName: "hotel-cancellation",
  modelVersion: "1",
  probability,
  isCanceled: probability >= 0.5,
  threshold: 0.5,
  latencyMs: 70,
  receivedAt: new Date().toISOString(),
})

// Simula as rotas de servidor no navegador; `health` e `predict` devolvem uma resposta por chamada.
export async function mockApi(
  page: Page,
  {
    health = [READY],
    predict = [prediction(0.42)],
  }: { health?: unknown[]; predict?: unknown[] } = {}
) {
  let h = 0
  let p = 0
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: health[Math.min(h++, health.length - 1)] })
  )
  await page.route("**/api/predict", (route) =>
    route.fulfill({ json: predict[Math.min(p++, predict.length - 1)] })
  )
}
