import type { Booking } from "./booking"
import categories from "./categories.json"

export type FieldName = keyof Booking

export type Option = { value: string; label: string }

export type FieldMeta = {
  name: FieldName
  label: string
  hint?: string
  unit?: string
} & (
  | { kind: "integer"; min?: number; max?: number }
  | { kind: "decimal"; min?: number; max?: number; step: number }
  // Vazio é enviado como null, que a API aceita nesses campos.
  | { kind: "nullable-number"; emptyLabel: string }
  | { kind: "select"; options: Option[] }
  | { kind: "nullable-select"; options: Option[]; emptyLabel: string }
  | { kind: "binary" }
)

export type FieldGroup = {
  id: string
  title: string
  description: string
  fields: FieldMeta[]
}

type CategoricalColumn = keyof typeof categories.columns

// Valores enviados à API são os do dataset; a tradução mostra o valor original entre parênteses.
const TRANSLATIONS: Partial<Record<CategoricalColumn, Record<string, string>>> =
  {
    hotel: { "City Hotel": "Hotel urbano", "Resort Hotel": "Resort" },
    meal: {
      BB: "Café da manhã",
      HB: "Meia pensão",
      FB: "Pensão completa",
      SC: "Sem refeição",
      Undefined: "Não definido",
    },
    market_segment: {
      "Online TA": "Agência online",
      "Offline TA/TO": "Agência ou operadora offline",
      Direct: "Direto",
      Groups: "Grupos",
      Corporate: "Corporativo",
      Complementary: "Cortesia",
      Aviation: "Aviação",
    },
    distribution_channel: {
      "TA/TO": "Agências e operadoras",
      Direct: "Direto",
      Corporate: "Corporativo",
      GDS: "GDS",
    },
    deposit_type: {
      "No Deposit": "Sem depósito",
      "Non Refund": "Não reembolsável",
      Refundable: "Reembolsável",
    },
    customer_type: {
      Transient: "Individual",
      "Transient-Party": "Individual ligado a grupo",
      Contract: "Contrato",
      Group: "Grupo",
    },
    reserved_room_type: {},
  }

function optionsFor(column: CategoricalColumn): Option[] {
  const names = TRANSLATIONS[column] ?? {}
  return categories.columns[column].frequent.map((value) => {
    const translated = names[value]
    const label =
      column === "reserved_room_type"
        ? `Tipo ${value}`
        : translated && translated !== value
          ? `${translated} (${value})`
          : value
    return { value, label }
  })
}

const MONTH_LABELS: Option[] = [
  ["January", "Janeiro"],
  ["February", "Fevereiro"],
  ["March", "Março"],
  ["April", "Abril"],
  ["May", "Maio"],
  ["June", "Junho"],
  ["July", "Julho"],
  ["August", "Agosto"],
  ["September", "Setembro"],
  ["October", "Outubro"],
  ["November", "Novembro"],
  ["December", "Dezembro"],
].map(([value, label]) => ({ value, label }))

export const CATEGORY_SOURCE = {
  modelVersion: categories.model_version,
  minFrequency: categories.min_frequency,
}

export const FIELD_GROUPS: FieldGroup[] = [
  {
    id: "estadia",
    title: "Estadia",
    description: "Hotel, datas de chegada e duração.",
    fields: [
      {
        name: "hotel",
        label: "Hotel",
        kind: "select",
        options: optionsFor("hotel"),
      },
      {
        name: "arrival_date_month",
        label: "Mês de chegada",
        kind: "select",
        options: MONTH_LABELS,
      },
      {
        name: "arrival_date_day_of_month",
        label: "Dia de chegada",
        kind: "integer",
        min: 1,
        max: 31,
      },
      {
        name: "arrival_date_week_number",
        label: "Semana do ano",
        hint: "Número da semana da chegada, de 1 a 53.",
        kind: "integer",
        min: 1,
        max: 53,
      },
      {
        name: "stays_in_weekend_nights",
        label: "Noites de fim de semana",
        kind: "integer",
        min: 0,
      },
      {
        name: "stays_in_week_nights",
        label: "Noites durante a semana",
        kind: "integer",
        min: 0,
      },
      {
        name: "reserved_room_type",
        label: "Tipo de quarto reservado",
        hint: "Os códigos são anonimizados no dataset.",
        kind: "select",
        options: optionsFor("reserved_room_type"),
      },
      {
        name: "meal",
        label: "Regime de refeição",
        kind: "select",
        options: optionsFor("meal"),
      },
    ],
  },
  {
    id: "hospedes",
    title: "Hóspedes",
    description: "Quem viaja e o que pediu.",
    fields: [
      { name: "adults", label: "Adultos", kind: "integer", min: 0 },
      {
        name: "children",
        label: "Crianças",
        kind: "nullable-number",
        emptyLabel: "Vazio = não informado",
      },
      { name: "babies", label: "Bebês", kind: "integer", min: 0 },
      {
        name: "country",
        label: "País de origem",
        hint: "Código ISO de 3 letras. Países fora da lista são tratados pelo modelo como infrequentes.",
        kind: "nullable-select",
        options: categories.columns.country.frequent.map((value) => ({
          value,
          label: value,
        })),
        emptyLabel: "Não informado",
      },
      {
        name: "customer_type",
        label: "Tipo de cliente",
        kind: "select",
        options: optionsFor("customer_type"),
      },
      {
        name: "required_car_parking_spaces",
        label: "Vagas de estacionamento",
        kind: "integer",
        min: 0,
      },
      {
        name: "total_of_special_requests",
        label: "Pedidos especiais",
        kind: "integer",
        min: 0,
      },
    ],
  },
  {
    id: "reserva",
    title: "Reserva",
    description: "Como e com que condições a reserva foi feita.",
    fields: [
      {
        name: "lead_time",
        label: "Antecedência",
        hint: "Dias entre a reserva e a chegada.",
        unit: "dias",
        kind: "integer",
        min: 0,
      },
      {
        name: "adr",
        label: "Diária média (ADR)",
        hint: "Valor médio por noite, menor que 1000.",
        kind: "decimal",
        min: 0,
        max: 999.99,
        step: 0.01,
      },
      {
        name: "deposit_type",
        label: "Depósito",
        kind: "select",
        options: optionsFor("deposit_type"),
      },
      {
        name: "market_segment",
        label: "Segmento de mercado",
        kind: "select",
        options: optionsFor("market_segment"),
      },
      {
        name: "distribution_channel",
        label: "Canal de distribuição",
        kind: "select",
        options: optionsFor("distribution_channel"),
      },
      {
        name: "agent",
        label: "Agente",
        hint: "ID anonimizado da agência.",
        kind: "nullable-number",
        emptyLabel: "Vazio = sem agente",
      },
      {
        name: "company",
        label: "Empresa",
        hint: "ID anonimizado da empresa pagadora.",
        kind: "nullable-number",
        emptyLabel: "Vazio = sem empresa",
      },
      {
        name: "booking_changes",
        label: "Alterações na reserva",
        kind: "integer",
        min: 0,
      },
      {
        name: "days_in_waiting_list",
        label: "Dias em lista de espera",
        kind: "integer",
        min: 0,
      },
    ],
  },
  {
    id: "historico",
    title: "Histórico",
    description: "Relação anterior do cliente com o hotel.",
    fields: [
      {
        name: "is_repeated_guest",
        label: "Hóspede recorrente",
        kind: "binary",
      },
      {
        name: "previous_cancellations",
        label: "Cancelamentos anteriores",
        kind: "integer",
        min: 0,
      },
      {
        name: "previous_bookings_not_canceled",
        label: "Reservas anteriores mantidas",
        kind: "integer",
        min: 0,
      },
    ],
  },
]

export const FIELD_LABELS = Object.fromEntries(
  FIELD_GROUPS.flatMap((g) => g.fields.map((f) => [f.name, f.label]))
) as Record<FieldName, string>
