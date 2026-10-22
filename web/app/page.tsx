import Link from "next/link"
import { ArrowRight } from "lucide-react"

import { ApiStatus } from "@/components/api-status"
import { PageHeader, Section } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { NAV_ITEMS } from "@/lib/navigation"

const SUMMARIES: Record<string, string> = {
  "/simular":
    "Preencha uma reserva, ou carregue um exemplo, e veja a probabilidade estimada pelo modelo publicado.",
  "/modelo":
    "Métricas do teste temporal, dataset, período de avaliação e decisões de engenharia.",
  "/lote":
    "Como o pipeline PySpark prepara features e calcula previsões em lote com o mesmo modelo.",
  "/arquitetura":
    "Fluxo dos dados, serviços Azure, CI/CD e documentação de operação.",
}

export default function Page() {
  return (
    <>
      <PageHeader
        title="Previsão de cancelamento de reservas"
        description="O hotelml é uma plataforma MLOps de referência: treino reprodutível, registry com champion e challenger, API FastAPI na Azure e pipelines Spark, tudo documentado."
        action={
          <Button asChild size="lg" className="px-4">
            <Link href="/simular">
              Simular reserva
              <ArrowRight data-icon="inline-end" />
            </Link>
          </Button>
        }
      />

      <div className="space-y-12">
        <Section
          title="Estado da API"
          description="Consulta em tempo real a /health/ready da API publicada na Azure."
        >
          <ApiStatus />
        </Section>

        <Section
          title="O que o modelo faz"
          description="Uma estimativa, não uma certeza."
        >
          <div className="max-w-3xl space-y-3 surface p-6 text-sm leading-relaxed">
            <p>
              A partir dos dados disponíveis no momento da reserva (estadia,
              hóspedes, canal de venda, depósito e histórico do cliente), o
              modelo estima a probabilidade de a reserva ser cancelada.
            </p>
            <p className="text-muted-foreground">
              Colunas que só existem depois do desfecho da reserva foram
              excluídas do treino para evitar vazamento de informação. A
              avaliação usa uma divisão temporal: o modelo treina no passado e é
              testado em reservas futuras.
            </p>
          </div>
        </Section>

        <Section title="Explorar">
          <ul className="grid gap-4 sm:grid-cols-2">
            {NAV_ITEMS.filter((item) => item.href !== "/").map(
              ({ href, label, icon: Icon }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="flex h-full flex-col gap-2 surface surface-interactive p-5"
                  >
                    <span className="flex items-center gap-2 font-medium">
                      <Icon
                        className="size-4 text-muted-foreground"
                        aria-hidden
                      />
                      {label}
                    </span>
                    <span className="text-sm leading-relaxed text-muted-foreground">
                      {SUMMARIES[href]}
                    </span>
                  </Link>
                </li>
              )
            )}
          </ul>
        </Section>
      </div>
    </>
  )
}
