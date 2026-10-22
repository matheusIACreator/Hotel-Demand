import type { Metadata } from "next"

import { PageHeader } from "@/components/page-header"
import { Simulator } from "@/components/simulator/simulator"

export const metadata: Metadata = { title: "Simular reserva" }

export default function Page() {
  return (
    <>
      <PageHeader
        title="Simular reserva"
        description="Descreva uma reserva e estime a probabilidade de cancelamento com o modelo carregado na API. Os campos seguem exatamente o contrato de /predict."
      />
      <Simulator />
    </>
  )
}
