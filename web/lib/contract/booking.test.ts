import { describe, expect, it } from "vitest"
import { z } from "zod"

import { bookingSchema } from "./booking"
import example from "./example-booking.json"
import openapi from "./openapi.json"

type JsonSchema = {
  type?: string
  anyOf?: JsonSchema[]
  enum?: unknown[]
  minimum?: number
  maximum?: number
  exclusiveMaximum?: number
  minLength?: number
  maxLength?: number
}

// Reduz um campo a um formato comparável: nulidade + restrições do tipo principal.
function normalize(schema: JsonSchema) {
  const variants = schema.anyOf ?? [schema]
  const nullable = variants.some((v) => v.type === "null")
  const main = variants.find((v) => v.type !== "null") ?? {}
  // O Zod descreve literais numéricos como "number"; um enum só de inteiros equivale a "integer".
  const integerEnum = main.enum?.every((v) => Number.isInteger(v))
  return {
    nullable,
    type: integerEnum ? "integer" : main.type,
    enum: main.enum,
    minimum: main.minimum,
    maximum: main.maximum,
    exclusiveMaximum: main.exclusiveMaximum,
    minLength: main.minLength,
    maxLength: main.maxLength,
  }
}

const api = openapi.components.schemas.Booking
const web = z.toJSONSchema(bookingSchema, { io: "input" }) as {
  properties: Record<string, JsonSchema>
  required: string[]
  additionalProperties: boolean
}

describe("contrato Booking", () => {
  it("tem exatamente os mesmos campos obrigatórios da API", () => {
    expect([...web.required].sort()).toEqual([...api.required].sort())
    expect(Object.keys(web.properties).sort()).toEqual(
      Object.keys(api.properties).sort()
    )
  })

  it("rejeita campos extras, como extra='forbid'", () => {
    expect(web.additionalProperties).toBe(false)
  })

  for (const [name, schema] of Object.entries(api.properties)) {
    it(`campo ${name} tem as mesmas restrições`, () => {
      const expected = normalize(schema as JsonSchema)
      const actual = normalize(web.properties[name])
      expect(actual.nullable).toBe(expected.nullable)
      expect(actual.type).toBe(expected.type)
      // O Zod pode ser mais estrito (ex.: enum de meses validado no model_validator da API),
      // mas nunca pode omitir uma restrição publicada no OpenAPI.
      for (const key of [
        "enum",
        "minimum",
        "maximum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
      ] as const) {
        if (expected[key] !== undefined) {
          expect(actual[key], key).toEqual(expected[key])
        }
      }
    })
  }

  it("aceita o exemplo sintético", () => {
    expect(bookingSchema.safeParse(example.booking).success).toBe(true)
  })

  it("exige pelo menos um hóspede", () => {
    const result = bookingSchema.safeParse({
      ...example.booking,
      adults: 0,
      children: null,
      babies: 0,
    })
    expect(result.success).toBe(false)
  })

  it("rejeita mês fora do formato da API", () => {
    const result = bookingSchema.safeParse({
      ...example.booking,
      arrival_date_month: "Julho",
    })
    expect(result.success).toBe(false)
  })
})
