// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import example from "@/lib/contract/example-booking.json"

import { checkHealth, predict, predictStatus } from "./hotelml-api"

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock)
  vi.stubEnv("HOTELML_API_URL", "https://api.example.test/")
})

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })

const timeout = () =>
  Promise.reject(new DOMException("signal timed out", "TimeoutError"))

describe("checkHealth", () => {
  it("devolve modelo e versão quando a API está pronta", async () => {
    fetchMock.mockResolvedValue(
      json({
        status: "ready",
        model_name: "hotel-cancellation",
        model_version: "1",
      })
    )
    const result = await checkHealth()
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/health/ready",
      expect.objectContaining({ cache: "no-store" })
    )
    expect(result).toMatchObject({
      state: "ready",
      modelName: "hotel-cancellation",
      modelVersion: "1",
    })
  })

  it("trata timeout como arranque a frio", async () => {
    fetchMock.mockImplementation(timeout)
    expect((await checkHealth()).state).toBe("starting")
  })

  it.each([502, 503, 504])(
    "trata %i como serviço iniciando",
    async (status) => {
      fetchMock.mockResolvedValue(
        json({ detail: "modelo indisponível" }, status)
      )
      expect((await checkHealth()).state).toBe("starting")
    }
  )

  it("aponta erro de configuração sem chamar a rede", async () => {
    vi.stubEnv("HOTELML_API_URL", "")
    const result = await checkHealth()
    expect(result.state).toBe("error")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("recusa resposta fora do formato", async () => {
    fetchMock.mockResolvedValue(json({ status: "ready" }))
    expect((await checkHealth()).state).toBe("error")
  })
})

describe("predict", () => {
  it("envia uma reserva e devolve probabilidade, decisão e versão", async () => {
    fetchMock.mockResolvedValue(
      json({
        model_name: "hotel-cancellation",
        model_version: "1",
        predictions: [{ cancellation_probability: 0.62, is_canceled: true }],
      })
    )
    const result = await predict(example.booking)
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({ bookings: [example.booking] })
    expect(result).toMatchObject({
      ok: true,
      probability: 0.62,
      isCanceled: true,
      modelVersion: "1",
      threshold: 0.5,
    })
    expect(predictStatus(result)).toBe(200)
  })

  it("valida localmente antes de chamar a API", async () => {
    const result = await predict({ ...example.booking, extra: 1 })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result).toMatchObject({ ok: false, kind: "validation" })
    expect(predictStatus(result)).toBe(422)
  })

  it("converte o 422 da FastAPI em mensagens por campo", async () => {
    fetchMock.mockResolvedValue(
      json(
        {
          detail: [
            {
              loc: ["body", "bookings", 0, "adr"],
              msg: "Input should be less than 1000",
            },
          ],
        },
        422
      )
    )
    const result = await predict(example.booking)
    expect(result).toMatchObject({
      ok: false,
      kind: "validation",
      issues: [{ field: "adr", message: "Input should be less than 1000" }],
    })
  })

  it("distingue arranque, timeout e falha da API", async () => {
    fetchMock.mockResolvedValueOnce(json({}, 503))
    expect(await predict(example.booking)).toMatchObject({ kind: "starting" })

    fetchMock.mockImplementationOnce(timeout)
    expect(await predict(example.booking)).toMatchObject({ kind: "timeout" })

    fetchMock.mockResolvedValueOnce(
      json({ detail: "falha na inferência" }, 500)
    )
    const failed = await predict(example.booking)
    expect(failed).toMatchObject({ kind: "upstream" })
    expect(predictStatus(failed)).toBe(502)
  })

  it("recusa probabilidade fora de [0, 1]", async () => {
    fetchMock.mockResolvedValue(
      json({
        model_name: "m",
        model_version: "1",
        predictions: [{ cancellation_probability: 1.4, is_canceled: true }],
      })
    )
    expect(await predict(example.booking)).toMatchObject({ kind: "upstream" })
  })
})
