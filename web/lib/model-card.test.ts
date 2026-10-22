import { describe, expect, it } from "vitest"

import categories from "@/lib/contract/categories.json"

import { METRIC_INFO, MODEL_CARD } from "./model-card"

describe("cartão do modelo", () => {
  it("tem descrição para cada métrica exportada, e só para elas", () => {
    expect(Object.keys(METRIC_INFO).sort()).toEqual(
      Object.keys(MODEL_CARD.metrics).sort()
    )
  })

  it("mantém as contagens consistentes", () => {
    const d = MODEL_CARD.dataset
    expect(d.train_rows + d.test_rows + d.removed_rows).toBe(d.raw_rows)
  })

  it("descreve a mesma versão das categorias do formulário", () => {
    expect(MODEL_CARD.source.model_version).toBe(categories.model_version)
    expect(MODEL_CARD.source.run_id).toBe(categories.run_id)
  })
})
