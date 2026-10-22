import { expect, test } from "@playwright/test"

import { READY, mockApi, prediction } from "./fixtures"

test("estima, altera a reserva e compara", async ({ page }) => {
  await mockApi(page, { predict: [prediction(0.84), prediction(0.31)] })
  await page.goto("/simular")

  await page.getByRole("button", { name: /carregar exemplo/i }).click()
  await page.getByRole("button", { name: "Estimar cancelamento" }).click()
  await expect(page.getByText("Cancelamento provável")).toBeVisible()
  await expect(page.getByText("84,0%")).toBeVisible()

  await page.getByLabel(/antecedência/i).fill("5")
  await page.getByRole("button", { name: "Estimar cancelamento" }).click()
  await expect(
    page.getByText("Comparação com a previsão anterior")
  ).toBeVisible()
  await expect(page.getByText("Campos alterados: Antecedência.")).toBeVisible()
  await expect(page.getByText("Manutenção provável")).toBeInViewport()
})

test("mostra a inicialização a frio e conclui a previsão", async ({ page }) => {
  await mockApi(page, {
    health: [
      { state: "starting", checkedAt: READY.checkedAt, detail: "" },
      READY,
    ],
    predict: [
      { ok: false, kind: "timeout", message: "demorou" },
      prediction(0.2),
    ],
  })
  await page.goto("/simular")
  await page.getByRole("button", { name: /carregar exemplo/i }).click()
  await page.getByRole("button", { name: "Estimar cancelamento" }).click()
  await expect(page.getByText(/Iniciando o serviço/)).toBeVisible()
  await expect(page.getByText("20,0%")).toBeVisible({ timeout: 15_000 })
})

test("envia o formulário pelo teclado", async ({ page }) => {
  await mockApi(page)
  await page.goto("/simular")
  await page.getByRole("button", { name: /carregar exemplo/i }).click()
  await page.getByLabel(/pedidos especiais/i).focus()
  await page.keyboard.press("Enter")
  await expect(page.getByText("42,0%")).toBeVisible()
})
