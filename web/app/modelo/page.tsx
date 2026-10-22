import type { Metadata } from "next"

import { PageHeader } from "@/components/page-header"

export const metadata: Metadata = { title: "Modelo" }

export default function Page() {
  return (
    <PageHeader
      title="Modelo"
      description="Como o modelo foi treinado e avaliado: dataset, divisão temporal, métricas e decisões de engenharia."
    />
  )
}
