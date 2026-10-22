import type { Metadata } from "next"

import { PageHeader } from "@/components/page-header"

export const metadata: Metadata = { title: "Processamento em lote" }

export default function Page() {
  return (
    <PageHeader
      title="Processamento em lote"
      description="Preparação de features e scoring distribuído com PySpark, reutilizando a validação e o modelo da API."
    />
  )
}
