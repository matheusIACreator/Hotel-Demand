import Link from "next/link"

import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <PageHeader
      title="Página não encontrada"
      description="O endereço não corresponde a nenhuma página desta interface."
      action={
        <Button asChild size="lg" className="px-4">
          <Link href="/">Voltar à visão geral</Link>
        </Button>
      }
    />
  )
}
