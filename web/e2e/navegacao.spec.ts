import { expect, test } from "@playwright/test"

import { mockApi } from "./fixtures"

test("visão geral mostra o estado real da API", async ({ page }) => {
  await mockApi(page)
  await page.goto("/")
  await expect(page.getByText("Serviço pronto")).toBeVisible()
  await expect(page.getByText("hotel-cancellation")).toBeVisible()
})

test("página inexistente usa a 404 da interface", async ({ page }) => {
  await page.goto("/nao-existe")
  await expect(
    page.getByRole("heading", { name: "Página não encontrada" })
  ).toBeVisible()
})

test("menu compacto navega no celular", async ({ page, isMobile }) => {
  test.skip(!isMobile, "só no celular")
  await mockApi(page)
  await page.goto("/")
  await page.getByRole("button", { name: "Abrir menu" }).click()
  await page.getByRole("dialog").getByRole("link", { name: "Modelo" }).click()
  await expect(
    page.getByRole("heading", { level: 1, name: "Modelo" })
  ).toBeVisible()
  await expect(page.getByRole("dialog")).toBeHidden()
})
