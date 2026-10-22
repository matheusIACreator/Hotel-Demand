import Link from "next/link"

import { StatusDot } from "@/components/status-dot"

// Só indicadores com fonte real; os restantes ficam explicitamente sem valor até existirem dados.
const AVAILABLE = [
  {
    name: "Estado da API",
    source: "GET /health/ready, consultado em tempo real",
  },
  {
    name: "Versão do modelo carregada",
    source: "GET /health/ready e resposta de /predict",
  },
  {
    name: "Tempo de resposta de um pedido",
    source: "Medido pelo servidor da interface em cada verificação ou previsão",
  },
]

const PENDING = [
  "Drift dos dados de entrada",
  "Qualidade dos dados em produção",
  "Latência agregada (percentis)",
  "Volume de pedidos",
  "Custos do ambiente",
]

export function OperationalIndicators() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-3 surface p-5">
        <h3 className="font-medium">Disponíveis agora</h3>
        <ul className="space-y-3 text-sm">
          {AVAILABLE.map((item) => (
            <li key={item.name} className="flex gap-2.5">
              <span className="mt-1.5">
                <StatusDot tone="success" />
              </span>
              <span>
                {item.name}
                <span className="block text-muted-foreground">
                  {item.source}
                </span>
              </span>
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted-foreground">
          Veja os valores atuais na{" "}
          <Link href="/" className="text-primary underline underline-offset-4">
            Visão geral
          </Link>{" "}
          e no simulador.
        </p>
      </div>
      <div className="space-y-3 surface p-5">
        <h3 className="font-medium">Sem fonte de dados ainda</h3>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {PENDING.map((name) => (
            <li key={name} className="flex items-center gap-2.5">
              <StatusDot tone="neutral" />
              {name}
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted-foreground">
          Dependem da fase 4 (monitoramento), ainda pendente. Nenhum valor é
          exibido até existirem dados reais.
        </p>
      </div>
    </div>
  )
}
