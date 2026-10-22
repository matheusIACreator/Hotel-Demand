const percent = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

const decimal = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})

const time = new Intl.DateTimeFormat("pt-BR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
})

export const formatPercent = (value: number) => percent.format(value)
export const formatMetric = (value: number) => decimal.format(value)
export const formatTime = (iso: string) => time.format(new Date(iso))
