import { cn } from "@/lib/utils"

export type Tone = "neutral" | "success" | "warning" | "danger"

const TONES: Record<Tone, string> = {
  neutral: "bg-muted-foreground/50",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
}

export function StatusDot({
  tone,
  pulse = false,
}: {
  tone: Tone
  pulse?: boolean
}) {
  return (
    <span className="relative flex size-2.5 shrink-0" aria-hidden>
      {pulse ? (
        <span
          className={cn(
            "absolute inline-flex size-full animate-ping rounded-full opacity-40 motion-reduce:hidden",
            TONES[tone]
          )}
        />
      ) : null}
      <span
        className={cn(
          "relative inline-flex size-2.5 rounded-full",
          TONES[tone]
        )}
      />
    </span>
  )
}
