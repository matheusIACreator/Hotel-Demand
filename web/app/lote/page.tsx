import type { Metadata } from "next"

import { DocLink, StepList } from "@/components/doc-link"
import { PageHeader, Section } from "@/components/page-header"
import { StatusDot } from "@/components/status-dot"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { DOCS } from "@/lib/links"

export const metadata: Metadata = { title: "Processamento em lote" }

const Code = ({ children }: { children: React.ReactNode }) => (
  <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[0.8em] text-foreground">
    {children}
  </code>
)

const OUTPUT = [
  ["booking_id", "ID estável da reserva, vindo do sistema de origem"],
  ["cancellation_probability", "Probabilidade de cancelamento"],
  ["is_canceled", "Decisão segundo o limiar"],
  ["model_name, model_version", "Identidade do snapshot usado"],
  ["threshold", "Limiar aplicado"],
  ["batch_id", "Identificador da execução, igual em todas as partições"],
  ["scored_at", "Instante UTC da execução"],
]

export default function Page() {
  return (
    <>
      <PageHeader
        title="Processamento em lote"
        description="Preparação de features e scoring distribuído com PySpark, reutilizando a validação, as features e o snapshot do modelo da API."
      />

      <div className="space-y-12">
        <div className="flex gap-3 surface p-5 text-sm leading-relaxed">
          <span className="mt-1.5">
            <StatusDot tone="neutral" />
          </span>
          <p>
            <span className="font-medium">
              Implementado e validado localmente.
            </span>{" "}
            <span className="text-muted-foreground">
              Não há cluster nem agendamento de jobs na Azure, e a API não expõe
              um endpoint de lote. Executar lotes por esta interface fica para
              uma etapa posterior, quando existir esse endpoint.
            </span>
          </p>
        </div>

        <Section title="Como o pipeline funciona">
          <div className="surface p-5 sm:p-6">
            <StepList
              steps={[
                {
                  title: "Entrada em Parquet",
                  text: (
                    <>
                      Todas as colunas do contrato de inferência e um{" "}
                      <Code>booking_id</Code> único e não vazio, fornecido pelo
                      sistema de origem. IDs nunca são gerados a partir da ordem
                      das partições.
                    </>
                  ),
                },
                {
                  title: "Preparação de features",
                  text: (
                    <>
                      <Code>hotelml features</Code> processa lotes Arrow com{" "}
                      <Code>mapInPandas</Code> (até 1000 linhas por lote). Cada
                      reserva passa pelo mesmo <Code>Booking</Code> da API e as
                      features vêm da função compartilhada{" "}
                      <Code>add_features</Code>. Alvo e colunas de vazamento são
                      excluídos.
                    </>
                  ),
                },
                {
                  title: "Scoring com o snapshot",
                  text: (
                    <>
                      <Code>hotelml batch</Code> recebe um bundle exportado; o
                      driver o distribui como ZIP aos executores e cada partição
                      carrega o modelo uma vez. O pipeline completo recalcula as
                      features, preservando a paridade com a API.
                    </>
                  ),
                },
                {
                  title: "Saída sem sobrescrita",
                  text: (
                    <>
                      Cada execução escreve num diretório novo. Um erro de dados
                      interrompe o lote inteiro, e só saídas com{" "}
                      <Code>_SUCCESS</Code> devem ser consumidas.
                    </>
                  ),
                },
              ]}
            />
          </div>
        </Section>

        <Section
          title="Colunas da saída de scoring"
          description="Relacione previsões e reservas pelo booking_id, nunca pela ordem das linhas."
        >
          <div className="surface p-2 sm:p-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Coluna</TableHead>
                  <TableHead>Conteúdo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {OUTPUT.map(([column, text]) => (
                  <TableRow key={column}>
                    <TableCell className="font-mono text-xs">
                      {column}
                    </TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">
                      {text}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>

        <Section title="Validação registrada">
          <ul className="space-y-2 surface p-5 text-sm leading-relaxed text-muted-foreground sm:p-6">
            <li>
              A preparação foi executada pela CLI sobre 200 reservas sintéticas,
              produzindo Parquet com 200 IDs únicos e 33 colunas.
            </li>
            <li>
              Os testes de integração Spark rodam num container com Java 21 e
              comparam features e previsões com o pipeline sklearn, incluindo
              valores ausentes, várias partições e lotes Arrow.
            </li>
            <li>
              Spark e Java são dependências opcionais: a imagem da API continua
              sem JVM.
            </li>
          </ul>
          <p className="text-sm">
            Detalhes: <DocLink href={DOCS.adrSpark}>ADR 0004</DocLink> ·{" "}
            <DocLink href={DOCS.runbookPipelines}>runbook de pipelines</DocLink>
          </p>
        </Section>
      </div>
    </>
  )
}
