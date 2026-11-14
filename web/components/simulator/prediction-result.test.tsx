import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PredictionPanel, SLOW_NOTICE_MS } from "./prediction-result"

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe("PredictionPanel durante o envio", () => {
  it("avisa da inicialização a frio quando a resposta demora", () => {
    render(<PredictionPanel run={{ phase: "sending" }} onRetry={() => {}} />)
    expect(screen.getByText("Calculando a estimativa…")).toBeInTheDocument()
    expect(screen.queryByText(/Iniciando o serviço/)).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(SLOW_NOTICE_MS)
    })
    expect(screen.getByText(/Iniciando o serviço/)).toBeInTheDocument()
    expect(
      screen.queryByText("Calculando a estimativa…")
    ).not.toBeInTheDocument()
  })

  it("recomeça a contagem a cada novo envio", () => {
    const { rerender } = render(
      <PredictionPanel run={{ phase: "sending" }} onRetry={() => {}} />
    )
    act(() => {
      vi.advanceTimersByTime(SLOW_NOTICE_MS)
    })
    rerender(<PredictionPanel run={{ phase: "idle" }} onRetry={() => {}} />)
    rerender(<PredictionPanel run={{ phase: "sending" }} onRetry={() => {}} />)
    expect(screen.getByText("Calculando a estimativa…")).toBeInTheDocument()
  })
})
