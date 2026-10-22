"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState } from "react"
import { Menu } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { NAV_ITEMS, isActive } from "@/lib/navigation"
import { cn } from "@/lib/utils"

function Brand() {
  return (
    <Link
      href="/"
      className="flex items-baseline gap-2 rounded-md px-1 text-foreground"
    >
      <span className="font-heading text-xl tracking-tight">hotelml</span>
      <span className="text-xs text-muted-foreground">cancelamentos</span>
    </Link>
  )
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  return (
    <ul className="flex flex-col gap-1">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href)
        return (
          <li key={href}>
            <Link
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors duration-150",
                "hover:bg-sidebar-accent hover:text-foreground",
                active && "bg-sidebar-accent font-medium text-foreground"
              )}
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {label}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="min-h-svh lg:grid lg:grid-cols-[15rem_1fr]">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded-md bg-card px-3 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Pular para o conteúdo
      </a>

      <aside className="sticky top-0 hidden h-svh flex-col gap-8 border-r border-sidebar-border bg-sidebar px-4 py-6 lg:flex">
        <Brand />
        <nav aria-label="Principal">
          <NavLinks />
        </nav>
        <p className="mt-auto px-1 text-xs leading-relaxed text-muted-foreground">
          Projeto de referência em MLOps. As previsões são estimativas, não
          certezas.
        </p>
      </aside>

      <header className="sticky top-0 z-40 flex items-center justify-between border-b bg-background/95 px-4 py-3 backdrop-blur-sm lg:hidden">
        <Brand />
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Abrir menu">
              <Menu />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 bg-sidebar">
            <SheetHeader>
              <SheetTitle className="font-heading text-xl">hotelml</SheetTitle>
              <SheetDescription>Navegação principal</SheetDescription>
            </SheetHeader>
            <nav aria-label="Principal" className="px-4">
              <NavLinks onNavigate={() => setOpen(false)} />
            </nav>
          </SheetContent>
        </Sheet>
      </header>

      <main id="conteudo" tabIndex={-1} className="min-w-0 outline-none">
        <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-8 lg:py-12">
          {children}
        </div>
      </main>
    </div>
  )
}
