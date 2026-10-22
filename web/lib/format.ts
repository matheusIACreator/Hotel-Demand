const percent = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

const decimal = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})

const integer = new Intl.NumberFormat("pt-BR")

const time = new Intl.DateTimeFormat("pt-BR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
})

// Datas sem hora (AAAA-MM-DD) são interpretadas em UTC para não mudarem de dia com o fuso.
const date = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" })

export const formatPercent = (value: number) => percent.format(value)
export const formatMetric = (value: number) => decimal.format(value)
export const formatInteger = (value: number) => integer.format(value)
export const formatTime = (iso: string) => time.format(new Date(iso))
export const formatDate = (iso: string) => date.format(new Date(iso))
