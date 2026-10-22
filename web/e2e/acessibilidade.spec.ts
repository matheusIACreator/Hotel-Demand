import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

import { mockApi } from "./fixtures"

// Sem animações, o axe avalia as cores finais e não um quadro intermediário da transição.
test.use({ reducedMotion: "reduce" })

const PAGES = ["/", "/simular", "/modelo", "/lote", "/arquitetura"]

for (const path of PAGES) {
  test(`${path} sem violações WCAG A/AA`, async ({ page }) => {
    await mockApi(page)
    await page.goto(path)
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze()
    expect(results.violations).toEqual([])
  })
}

test("simulador com erros e resultado continua acessível", async ({ page }) => {
  await mockApi(page)
  await page.goto("/simular")
  await page.getByRole("button", { name: "Estimar cancelamento" }).click()
  await expect(page.getByRole("alert").first()).toBeVisible()
  await page.getByRole("button", { name: /carregar exemplo/i }).click()
  await page.getByRole("button", { name: "Estimar cancelamento" }).click()
  await expect(page.getByText("42,0%")).toBeVisible()
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze()
  expect(results.violations).toEqual([])
})

test("link para pular a navegação recebe o foco primeiro", async ({ page }) => {
  await mockApi(page)
  await page.goto("/modelo")
  await page.keyboard.press("Tab")
  const skip = page.getByRole("link", { name: "Pular para o conteúdo" })
  await expect(skip).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/#conteudo$/)
})
