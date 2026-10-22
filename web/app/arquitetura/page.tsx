import type { Metadata } from "next"

import { PageHeader } from "@/components/page-header"

export const metadata: Metadata = { title: "Arquitetura e operação" }

export default function Page() {
  return (
    <PageHeader
      title="Arquitetura e operação"
      description="Do treino ao serving: registry, bundle imutável, imagem no ACR, Container Apps e CI/CD."
    />
  )
}
