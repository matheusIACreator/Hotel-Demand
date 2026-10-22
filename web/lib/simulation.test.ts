import { describe, expect, it } from "vitest"

import example from "@/lib/contract/example-booking.json"
import type { Booking } from "@/lib/contract/booking"

import { changedFields, deltaPoints, formatPoints } from "./simulation"

const base = example.booking as Booking

describe("comparação de simulações", () => {
  it("lista apenas os campos alterados", () => {
    expect(changedFields(base, { ...base })).toEqual([])
    expect(
      changedFields(base, {
        ...base,
        lead_time: 10,
        deposit_type: "Non Refund",
      })
    ).toEqual(["lead_time", "deposit_type"])
  })

  it("trata null e 0 como valores diferentes", () => {
    expect(changedFields(base, { ...base, children: null })).toEqual([
      "children",
    ])
  })

  it("formata a variação em pontos percentuais", () => {
    expect(formatPoints(deltaPoints(0.62, 0.84))).toBe("+22,0 p.p.")
    expect(formatPoints(deltaPoints(0.84, 0.62))).toBe("−22,0 p.p.")
    expect(formatPoints(deltaPoints(0.5, 0.50001))).toBe("sem variação")
  })
})
