import {
  BedDouble,
  ChartNoAxesColumn,
  House,
  Layers,
  Network,
  type LucideIcon,
} from "lucide-react"

export type NavItem = {
  href: string
  label: string
  icon: LucideIcon
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Visão geral", icon: House },
  { href: "/simular", label: "Simular reserva", icon: BedDouble },
  { href: "/modelo", label: "Modelo", icon: ChartNoAxesColumn },
  { href: "/lote", label: "Processamento em lote", icon: Layers },
  { href: "/arquitetura", label: "Arquitetura e operação", icon: Network },
]

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href)
}
