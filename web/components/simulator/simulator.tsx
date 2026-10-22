"use client"

import { useRef, useState } from "react"
import { useForm, useWatch } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Eraser, FileInput, Loader2 } from "lucide-react"

import { BookingFields } from "@/components/simulator/booking-form"
import {
  PredictionPanel,
  type RunPhase,
} from "@/components/simulator/prediction-result"
import { Button } from "@/components/ui/button"
import { waitForApi } from "@/hooks/use-api-health"
import type { PredictFailure, PredictResult } from "@/lib/api-types"
import { bookingSchema, type Booking } from "@/lib/contract/booking"
import example from "@/lib/contract/example-booking.json"
import { FIELD_LABELS, type FieldName } from "@/lib/contract/fields"
import { changedFields, type Simulation } from "@/lib/simulation"

// Contadores começam em zero; o restante fica vazio até o usuário preencher ou carregar o exemplo.
const EMPTY: Partial<Booking> = {
  children: 0,
  babies: 0,
  country: null,
  agent: null,
  company: null,
  is_repeated_guest: 0,
  previous_cancellations: 0,
  previous_bookings_not_canceled: 0,
  booking_changes: 0,
  days_in_waiting_list: 0,
  required_car_parking_spaces: 0,
  total_of_special_requests: 0,
}

async function postPredict(booking: Booking): Promise<PredictResult> {
  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking }),
    })
    return (await response.json()) as PredictResult
  } catch {
    return {
      ok: false,
      kind: "upstream",
      message: "Não foi possível falar com o servidor da interface.",
    }
  }
}

const needsWake = (r: PredictResult): r is PredictFailure =>
  !r.ok && (r.kind === "starting" || r.kind === "timeout")

export function Simulator() {
  const form = useForm<Booking>({
    resolver: zodResolver(bookingSchema),
    defaultValues: EMPTY,
    mode: "onSubmit",
    reValidateMode: "onChange",
  })
  const [run, setRun] = useState<RunPhase>({ phase: "idle" })
  const [history, setHistory] = useState<{
    current?: Simulation
    previous?: Simulation
  }>({})
  const [exampleLoaded, setExampleLoaded] = useState(false)
  const [lastBooking, setLastBooking] = useState<Booking | null>(null)
  const values = useWatch({ control: form.control })
  const panel = useRef<HTMLDivElement>(null)

  // No celular o resultado fica abaixo do formulário; no desktop o painel fixo já está visível.
  function revealPanel() {
    requestAnimationFrame(() => {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)")
      panel.current?.scrollIntoView({
        block: "nearest",
        behavior: reduce.matches ? "auto" : "smooth",
      })
    })
  }

  const pending = history.current
    ? changedFields(history.current.booking, {
        ...history.current.booking,
        ...values,
      } as Booking)
    : []

  async function estimate(booking: Booking) {
    setLastBooking(booking)
    setRun({ phase: "sending" })
    let result = await postPredict(booking)

    if (needsWake(result)) {
      const since = Date.now()
      setRun({ phase: "waking", since })
      const health = await waitForApi(() => setRun({ phase: "waking", since }))
      result =
        health.status === "ready"
          ? await postPredict(booking)
          : {
              ok: false,
              kind: "starting",
              message:
                health.status === "unavailable"
                  ? health.detail
                  : "O serviço não ficou disponível.",
            }
    }

    if (result.ok) {
      const success = result
      setHistory((h) => ({
        previous: h.current,
        current: { booking, result: success },
      }))
      setRun({ phase: "idle" })
      revealPanel()
      return
    }

    for (const issue of result.issues ?? []) {
      if (issue.field && issue.field in FIELD_LABELS) {
        form.setError(issue.field as FieldName, { message: issue.message })
      }
    }
    setRun({ phase: "error", failure: result })
    revealPanel()
  }

  function loadExample() {
    form.reset(example.booking as Booking)
    setExampleLoaded(true)
  }

  function clear() {
    form.reset(EMPTY)
    setExampleLoaded(false)
  }

  const busy = run.phase === "sending" || run.phase === "waking"

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <form
        noValidate
        onSubmit={(event) => void form.handleSubmit(estimate)(event)}
        aria-label="Dados da reserva"
        className="space-y-6"
      >
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" onClick={loadExample}>
            <FileInput data-icon="inline-start" />
            Carregar exemplo
          </Button>
          <Button type="button" variant="ghost" onClick={clear}>
            <Eraser data-icon="inline-start" />
            Limpar
          </Button>
          <p className="basis-full text-xs text-muted-foreground" role="status">
            {exampleLoaded ? example.source : null}
          </p>
        </div>

        <BookingFields
          register={form.register}
          errors={form.formState.errors}
        />

        <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center gap-3 rounded-xl border bg-background/95 p-3 backdrop-blur-sm">
          <Button type="submit" size="lg" className="px-5" disabled={busy}>
            {busy ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : null}
            Estimar cancelamento
          </Button>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {history.current && pending.length > 0
              ? `${pending.length} ${pending.length === 1 ? "campo alterado" : "campos alterados"} desde a última estimativa.`
              : null}
          </p>
        </div>
      </form>

      <div ref={panel} className="scroll-mt-20 lg:sticky lg:top-6">
        <PredictionPanel
          run={run}
          current={history.current}
          previous={history.previous}
          onRetry={() => {
            if (lastBooking) void estimate(lastBooking)
          }}
        />
      </div>
    </div>
  )
}
