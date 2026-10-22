import { ExternalLink } from "lucide-react"

import { cn } from "@/lib/utils"

export function DocLink({
  href,
  children,
  className,
}: {
  href: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={cn(
        "inline-flex items-center gap-1 text-primary underline underline-offset-4",
        className
      )}
    >
      {children}
      <ExternalLink className="size-3" aria-hidden />
      <span className="sr-only">(abre em nova aba)</span>
    </a>
  )
}

export function StepList({
  steps,
}: {
  steps: { title: string; text: React.ReactNode }[]
}) {
  return (
    <ol className="space-y-0">
      {steps.map((step, i) => (
        <li key={step.title} className="relative flex gap-4 pb-6 last:pb-0">
          {i < steps.length - 1 ? (
            <span
              className="absolute top-8 bottom-0 left-3.5 w-px bg-border"
              aria-hidden
            />
          ) : null}
          <span
            className="z-10 flex size-7 shrink-0 items-center justify-center rounded-full border bg-card text-sm font-medium tabular-nums"
            aria-hidden
          >
            {i + 1}
          </span>
          <div className="space-y-1 pt-0.5">
            <p className="font-medium">{step.title}</p>
            <div className="text-sm leading-relaxed text-muted-foreground">
              {step.text}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}
