import type { Metadata } from "next"
import { Geist, Geist_Mono, Newsreader } from "next/font/google"

import "./globals.css"
import { AppShell } from "@/components/app-shell"
import { TooltipProvider } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const sans = Geist({ subsets: ["latin"], variable: "--font-sans" })
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" })
// Serifada apenas nos títulos; tabelas e formulários permanecem em sans-serif.
const heading = Newsreader({
  subsets: ["latin"],
  variable: "--font-heading",
  weight: ["400", "500"],
})

export const metadata: Metadata = {
  title: {
    default: "hotelml · cancelamento de reservas",
    template: "%s · hotelml",
  },
  description:
    "Interface do hotelml: simulação de cancelamento de reservas de hotel com a API publicada na Azure.",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="pt-BR"
      className={cn(
        "antialiased",
        sans.variable,
        mono.variable,
        heading.variable
      )}
    >
      <body>
        <TooltipProvider>
          <AppShell>{children}</AppShell>
        </TooltipProvider>
      </body>
    </html>
  )
}
