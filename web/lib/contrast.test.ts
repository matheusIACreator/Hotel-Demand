import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

import { contrastRatio } from "./contrast"

// Lê a paleta diretamente do CSS, para que o teste acompanhe qualquer mudança de cor.
const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8")
const palette = Object.fromEntries(
  [...css.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/gi)].map((m) => [m[1], m[2]])
)

const SURFACES = ["sand-50", "snow"] as const
// Texto normal exige 4,5:1 (WCAG AA).
const TEXT = [
  "ink",
  "ink-muted",
  "walnut",
  "olive",
  "amber",
  "terracotta",
] as const

describe("paleta", () => {
  it("define todas as cores esperadas", () => {
    for (const name of [...SURFACES, ...TEXT, "sand-200", "sand-300"]) {
      expect(palette[name], name).toMatch(/^#/)
    }
  })

  for (const surface of SURFACES) {
    for (const text of TEXT) {
      it(`${text} sobre ${surface} atinge AA`, () => {
        expect(
          contrastRatio(palette[text], palette[surface])
        ).toBeGreaterThanOrEqual(4.5)
      })
    }
  }

  it("texto secundário sobre areia atinge AA", () => {
    expect(
      contrastRatio(palette["ink-muted"], palette["sand-200"])
    ).toBeGreaterThanOrEqual(4.5)
  })

  it("texto do botão principal atinge AA, também no hover", () => {
    expect(
      contrastRatio(palette.snow, palette["walnut-deep"])
    ).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(palette.snow, palette.walnut)).toBeGreaterThanOrEqual(
      4.5
    )
  })
})
