import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ApiStatusView } from "./api-status"

describe("ApiStatusView", () => {
  it("mostra a mensagem de arranque a frio", () => {
    render(
      <ApiStatusView
        view={{ status: "starting", since: Date.now(), detail: "" }}
        onRetry={() => {}}
      />
    )
    expect(screen.getByText("Iniciando o serviço…")).toBeInTheDocument()
  })

  it("mostra modelo e versão reais quando pronta", () => {
    render(
      <ApiStatusView
        view={{
          status: "ready",
          result: {
            state: "ready",
            modelName: "hotel-cancellation",
            modelVersion: "1",
            checkedAt: "2026-10-22T10:00:00Z",
            latencyMs: 120,
          },
        }}
        onRetry={() => {}}
      />
    )
    expect(screen.getByText("hotel-cancellation")).toBeInTheDocument()
    expect(screen.getByText("1")).toBeInTheDocument()
    expect(screen.getByText("120 ms")).toBeInTheDocument()
  })

  it("permite tentar novamente quando indisponível", async () => {
    const onRetry = vi.fn()
    render(
      <ApiStatusView
        view={{ status: "unavailable", detail: "falhou" }}
        onRetry={onRetry}
      />
    )
    await userEvent.click(
      screen.getByRole("button", { name: /tentar novamente/i })
    )
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
