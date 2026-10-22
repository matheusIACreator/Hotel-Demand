import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Simulator } from "./simulator"

const fetchMock = vi.fn()

beforeEach(() => vi.stubGlobal("fetch", fetchMock))
afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

const reply = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }))

const success = (probability: number) => ({
  ok: true,
  modelName: "hotel-cancellation",
  modelVersion: "1",
  probability,
  isCanceled: probability >= 0.5,
  threshold: 0.5,
  latencyMs: 80,
  receivedAt: new Date().toISOString(),
})

describe("Simulator", () => {
  it("não chama a API com o formulário vazio", async () => {
    render(<Simulator />)
    await userEvent.click(
      screen.getByRole("button", { name: "Estimar cancelamento" })
    )
    expect(await screen.findAllByRole("alert")).not.toHaveLength(0)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("estima com o exemplo e compara com a previsão anterior", async () => {
    const user = userEvent.setup()
    fetchMock
      .mockImplementationOnce(() => reply(success(0.84)))
      .mockImplementationOnce(() => reply(success(0.31)))
    render(<Simulator />)

    await user.click(screen.getByRole("button", { name: /carregar exemplo/i }))
    await user.click(
      screen.getByRole("button", { name: "Estimar cancelamento" })
    )
    expect(await screen.findByText("84,0%")).toBeInTheDocument()
    expect(screen.getByText("Cancelamento provável")).toBeInTheDocument()

    const [, init] = fetchMock.mock.calls[0]
    const sent = JSON.parse(init.body).booking
    expect(sent.hotel).toBe("City Hotel")
    expect(sent.company).toBeNull()

    const lead = screen.getByLabelText(/antecedência/i)
    await user.clear(lead)
    await user.type(lead, "5")
    expect(
      screen.getByText("1 campo alterado desde a última estimativa.")
    ).toBeInTheDocument()

    await user.click(
      screen.getByRole("button", { name: "Estimar cancelamento" })
    )
    expect(await screen.findAllByText("31,0%")).toHaveLength(2)
    expect(screen.getByText(/−53,0 p\.p\./)).toBeInTheDocument()
    expect(
      screen.getByText("Campos alterados: Antecedência.")
    ).toBeInTheDocument()
  })

  it("aguarda o arranque da API e repete a previsão", async () => {
    const user = userEvent.setup()
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/health") {
        return reply({
          state: "ready",
          modelName: "hotel-cancellation",
          modelVersion: "1",
          checkedAt: new Date().toISOString(),
          latencyMs: 50,
        })
      }
      return fetchMock.mock.calls.filter(([u]) => u === "/api/predict")
        .length === 1
        ? reply({ ok: false, kind: "timeout", message: "demorou" }, 504)
        : reply(success(0.2))
    })
    render(<Simulator />)

    await user.click(screen.getByRole("button", { name: /carregar exemplo/i }))
    await user.click(
      screen.getByRole("button", { name: "Estimar cancelamento" })
    )
    expect(await screen.findByText("20,0%")).toBeInTheDocument()
    expect(screen.getByText("Manutenção provável")).toBeInTheDocument()
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual([
      "/api/predict",
      "/api/health",
      "/api/predict",
    ])
  })

  it("marca no formulário os campos recusados pela API", async () => {
    const user = userEvent.setup()
    fetchMock.mockImplementation(() =>
      reply(
        {
          ok: false,
          kind: "validation",
          message: "A API recusou a reserva.",
          issues: [{ field: "adr", message: "Input should be less than 1000" }],
        },
        422
      )
    )
    render(<Simulator />)
    await user.click(screen.getByRole("button", { name: /carregar exemplo/i }))
    await user.click(
      screen.getByRole("button", { name: "Estimar cancelamento" })
    )
    await waitFor(() =>
      expect(screen.getByLabelText(/diária média/i)).toHaveAttribute(
        "aria-invalid",
        "true"
      )
    )
    expect(
      screen.getByText("Input should be less than 1000")
    ).toBeInTheDocument()
  })
})
