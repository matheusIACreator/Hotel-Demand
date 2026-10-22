import { formatDate, formatInteger } from "@/lib/format"
import { daysBetween } from "@/lib/model-card"

type Props = {
  trainStart: string
  cutoff: string
  testEnd: string
  trainRows: number
  testRows: number
}

export function SplitTimeline({
  trainStart,
  cutoff,
  testEnd,
  trainRows,
  testRows,
}: Props) {
  const total = daysBetween(trainStart, testEnd)
  const trainShare = (daysBetween(trainStart, cutoff) / total) * 100

  return (
    <figure className="space-y-3">
      <div className="flex h-9 overflow-hidden rounded-lg border" aria-hidden>
        <div
          className="flex items-center bg-secondary px-3 text-xs font-medium"
          style={{ width: `${trainShare}%` }}
        >
          Treino
        </div>
        <div className="flex flex-1 items-center justify-center border-l border-dashed border-foreground/40 bg-card px-2 text-xs font-medium">
          Teste
        </div>
      </div>
      <figcaption>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Treino (passado)</dt>
            <dd className="tabular-nums">
              {formatDate(trainStart)} a {formatDate(cutoff)} ·{" "}
              {formatInteger(trainRows)} reservas
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Teste (futuro)</dt>
            <dd className="tabular-nums">
              {formatDate(cutoff)} a {formatDate(testEnd)} ·{" "}
              {formatInteger(testRows)} reservas
            </dd>
          </div>
        </dl>
      </figcaption>
    </figure>
  )
}
