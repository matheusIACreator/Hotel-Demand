import { describe, expect, it } from "vitest"

import openapi from "./openapi.json"
import example from "./example-booking.json"
import { FIELD_GROUPS } from "./fields"

describe("grupos do formulário", () => {
  const names = FIELD_GROUPS.flatMap((g) => g.fields.map((f) => f.name))

  it("cobrem cada campo do contrato exatamente uma vez", () => {
    expect([...names].sort()).toEqual(
      Object.keys(openapi.components.schemas.Booking.properties).sort()
    )
    expect(new Set(names).size).toBe(names.length)
  })

  it("oferecem os valores do exemplo nas listas", () => {
    for (const field of FIELD_GROUPS.flatMap((g) => g.fields)) {
      if (field.kind !== "select" && field.kind !== "nullable-select") continue
      const value = example.booking[field.name]
      if (value === null) continue
      expect(
        field.options.map((o) => o.value),
        field.name
      ).toContain(value)
    }
  })
})
