import { z } from "zod"

/*
 * Espelho do `Booking` de src/hotelml/api.py. O teste booking.test.ts compara este schema com
 * openapi.json, exportado da própria FastAPI; se o backend mudar, o teste falha.
 */

export const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const

const count = (label: string) =>
  z
    .int({ error: `${label}: informe um número inteiro.` })
    .min(0, { error: `${label}: não pode ser negativo.` })

const text = (label: string) =>
  z
    .string({ error: `${label}: obrigatório.` })
    .min(1, { error: `${label}: obrigatório.` })
    .max(100, { error: `${label}: até 100 caracteres.` })

const optionalNumber = (label: string) =>
  z
    .number({ error: `${label}: informe um número ou deixe vazio.` })
    .min(0, { error: `${label}: não pode ser negativo.` })
    .nullable()

export const bookingSchema = z
  .strictObject({
    hotel: text("Hotel"),
    lead_time: count("Antecedência"),
    arrival_date_month: z.enum(MONTHS, {
      error: "Mês de chegada inválido.",
    }),
    arrival_date_week_number: z
      .int({ error: "Semana: informe um número inteiro." })
      .min(1, { error: "Semana: entre 1 e 53." })
      .max(53, { error: "Semana: entre 1 e 53." }),
    arrival_date_day_of_month: z
      .int({ error: "Dia: informe um número inteiro." })
      .min(1, { error: "Dia: entre 1 e 31." })
      .max(31, { error: "Dia: entre 1 e 31." }),
    stays_in_weekend_nights: count("Noites de fim de semana"),
    stays_in_week_nights: count("Noites durante a semana"),
    adults: count("Adultos"),
    children: optionalNumber("Crianças"),
    babies: count("Bebês"),
    meal: text("Regime de refeição"),
    country: z
      .string()
      .max(100, { error: "País: até 100 caracteres." })
      .nullable(),
    market_segment: text("Segmento de mercado"),
    distribution_channel: text("Canal de distribuição"),
    is_repeated_guest: z.literal([0, 1], {
      error: "Hóspede recorrente: escolha sim ou não.",
    }),
    previous_cancellations: count("Cancelamentos anteriores"),
    previous_bookings_not_canceled: count("Reservas anteriores mantidas"),
    reserved_room_type: text("Tipo de quarto"),
    booking_changes: count("Alterações na reserva"),
    deposit_type: text("Depósito"),
    agent: optionalNumber("Agente"),
    company: optionalNumber("Empresa"),
    days_in_waiting_list: count("Dias em lista de espera"),
    customer_type: text("Tipo de cliente"),
    adr: z
      .number({ error: "Diária média: informe um valor." })
      .min(0, { error: "Diária média: não pode ser negativa." })
      .lt(1000, { error: "Diária média: deve ser menor que 1000." }),
    required_car_parking_spaces: count("Vagas de estacionamento"),
    total_of_special_requests: count("Pedidos especiais"),
  })
  .refine((b) => b.adults + (b.children ?? 0) + b.babies > 0, {
    error: "A reserva deve ter pelo menos um hóspede.",
    path: ["adults"],
  })

export type Booking = z.infer<typeof bookingSchema>

// Formato de `PredictResponse` com uma única reserva, como o simulador a envia.
export const predictResponseSchema = z.object({
  model_name: z.string(),
  model_version: z.string(),
  predictions: z
    .array(
      z.object({
        cancellation_probability: z.number().min(0).max(1),
        is_canceled: z.boolean(),
      })
    )
    .length(1),
})

export const readyResponseSchema = z.object({
  status: z.literal("ready"),
  model_name: z.string(),
  model_version: z.string(),
})

// Limiar fixo em `api.py` (p >= 0,5); a API não o devolve na resposta.
export const DECISION_THRESHOLD = 0.5
