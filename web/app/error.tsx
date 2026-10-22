"use client"

import { RotateCw } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <PageHeader
      title="Algo deu errado"
      description="Esta página encontrou um erro inesperado. Os dados da API não foram alterados."
      action={
        <Button size="lg" className="px-4" onClick={reset}>
          <RotateCw data-icon="inline-start" />
          Tentar novamente
        </Button>
      }
    />
  )
}
