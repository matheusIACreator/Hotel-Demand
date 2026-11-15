# Operar o piloto de disponibilidade externa

## Piloto 1 (encerrado)

`external-20261109` correu de 09/11/2026 às 21:17 UTC até o slot 121 (14/11). As 17 principais
coletadas falharam: o proxy desistia aos 20 s e o arranque a frio levava 45 a 55 s. O sistema
foi corrigido no slot 122 e esses resultados não se agregam aos seguintes. Causa, medições e
slots a excluir: [validação de 2026-11-15](../validation/arranque-frio-2026-11-15.md).

## Janela do piloto 2

Proposta no [ADR 0013](../adr/0013-arranque-frio-e-piloto-2.md); vale a partir do merge na `main`.

- Início: **16/11/2026 às 00:17 UTC**, também 00:17 em Lisboa nesta data.
- Fim de novas tentativas: **30/11/2026 às 00:17 UTC**, exclusivo.
- Uma principal por hora; somente após falha, até dois diagnósticos.
- Até 72 inferências por dia completo; retenção dos artefatos: 30 dias.
- Origem: `https://hotelml.vercel.app`; modelo esperado: versão 1.
- Timeout do coletor: **60 s**, acima do arranque a frio medido (~31 s) e do proxy (50 s).

O workflow só agenda pela branch padrão depois de publicado na `main`. Código apenas local
ou numa PR não ativa o piloto. A configuração está em `monitoring/external-pilot.json`.
Entre o merge e o início não há tráfego; se o merge ocorrer depois do início, os slots já
passados ficam como lacuna. Não altere datas, versão ou limites no decorrer do piloto sem
registrar uma nova decisão.

## Acompanhar

Abra **Actions → Piloto de sondagem externa**. O cron usa o minuto 17; atrasos podem ocorrer.
O coletor rejeita reexecuções, dispatch manual, runs duplicados do mesmo slot e runs que
chegaram ao próximo slot. Não use re-run para substituir uma falha por um sucesso.
Chamadas do slot de ontem não podem iniciar no dia UTC seguinte; isso preserva o limite diário.

Em cada execução, consulte:

1. `probe-external-20261116-<slot>-success|failure|incomplete`: contém principal e diagnósticos
   em subdiretórios separados. `primary/_SUCCESS` confirma coleta da principal, não saúde.
2. `pilot.json`: resumo que preserva o resultado principal mesmo se os diagnósticos recuperarem.
3. `audit-external-20261116-<run>-<attempt>`: cobertura dos slots e lacunas em `audit.json`.

O agendador do GitHub não garante um run por hora: no piloto 1 entregou 14% dos slots. Slots
sem run são lacunas de coleta e aparecem como `missing` na auditoria.

O job de coleta falha quando a principal falha, mas os artefatos são enviados com `always()`.
Se a instalação, runner ou upload falharem, não conclua que houve indisponibilidade da API.
Depois de noventa minutos, a ausência do artefato é uma lacuna de coleta. Artefatos duplicados
são sinalizados e não entram como sucesso. Arquivos expirados também deixam de ser evidência
disponível: faça a revisão final dentro da retenção.

Para atualizar a auditoria sem gerar tráfego, execute **Run workflow** manualmente na `main`.
Isso ajuda a verificar lacunas se uma execução agendada não ocorreu. Se o Actions parar por
completo, não há detecção independente em tempo real; confira o histórico durante o piloto.

## Investigar falhas

Compare o journal da principal com os diagnósticos e os logs internos da mesma janela.
Uma recuperação diagnóstica não altera a falha principal nem entra na sua taxa de sucesso.
Não subtraia percentis para atribuir tempo ao proxy. O [ensaio inicial](../validation/sondagem-2026-11-08.md)
mostrou 504 externos e 200 internos na janela: ambas as perspectivas são necessárias.

Valide revisão, versão do modelo e motivo operacional antes de qualquer mudança. A leitura
esperada depois da correção:

- **Sucesso em ~30 s:** a principal acordou a API. É o comportamento normal com escala a zero.
- **Sucesso em menos de 2 s:** a réplica já estava ativa; confira se houve outro tráfego.
- **HTTP 504 perto dos 50 s:** o proxy esgotou a espera. Veja nos logs de sistema quanto
  demorou o pull da imagem e o arranque do container.
- **`timeout` aos 60 s:** nem o proxy respondeu; investigue a Vercel antes da API.

Para a linha do tempo de um arranque, consulte `ContainerAppSystemLogs_CL` e os eventos
`model_loading`, `model_ready` e `http_request` na janela do slot, como na validação.

## Encerrar ou interromper

O gate bloqueia novas tentativas no fim da janela. A última auditoria precisa aguardar a
tolerância do último slot; a primeira execução horária elegível para desativar o workflow é
**30/11 às 01:17 UTC**. O job de encerramento desativa o agendamento via API GitHub.

Se precisar interromper antes, use **Disable workflow** na página do workflow. Se o último
run não ocorrer ou não tiver permissão para desativar, faça isso manualmente. Mesmo nesse
caso, o gate temporal impede novas tentativas depois do fim; jobs de auditoria ainda podem
rodar até a desativação.

## Revisar os resultados

Revise resultados principais e cobertura separadamente. Slots ausentes são desconhecidos,
não sucesso nem falha de disponibilidade. Compare a primeira tentativa com os diagnósticos,
preserve timeouts e confira custos de réplica, logs, artefatos e runner. O orçamento de
requisições não garante o orçamento financeiro Azure.

Baixe os artefatos dentro da retenção, um diretório por artefato, e gere o resumo. O `review`
só lê arquivos locais. O download com `gh` abaixo não foi executado na validação, feita numa
máquina sem essa ferramenta; qualquer forma de obter os diretórios com o nome original serve:

```powershell
gh run download --repo matheusIACreator/Hotel-Demand --pattern 'probe-external-20261116-*' --dir data/reports/pilot-2-artifacts
.venv/Scripts/python scripts/probe_pilot.py review --artifacts data/reports/pilot-2-artifacts --slo monitoring/slo-policy.json --output data/reports/pilot-2-review.json
```

`review.json` traz, por slot, resultado, status HTTP e duração da principal, os diagnósticos e
o tempo até a recuperação, além de percentis das durações. Artefatos sem `_SUCCESS` na
principal ou duplicados ficam em `skipped_artifacts` e fora das estatísticas.

## Avaliar as metas

As metas ficam em `monitoring/slo-policy.json` e são fixadas antes da avaliação. Com
`status: proposed`, o relatório mostra as taxas e deixa `met` nulo (`policy_not_approved`).
Para aprovar, o responsável muda o estado para `approved` num commit **anterior** ao fim do
piloto; aprovar depois de ver os resultados invalida a avaliação.

| `evaluation.status` | Significado |
| --- | --- |
| `policy_not_approved` | Metas ainda propostas; sem veredito |
| `insufficient_data` | Menos principais que o mínimo; sem veredito |
| `wrong_pilot` | A política refere outro piloto |
| `ready` | Volume suficiente e política aprovada; confira `success.met` e `duration.met` |

O código de saída 2 indica meta violada com `ready`; nos outros casos é 0, e a automação deve
ler `status`. Falhas contam contra as duas metas. A taxa descreve a primeira chamada de cada
slot coletado; não é disponibilidade mensal nem cobre os slots sem run.

Aprovar metas externas ou mudar a política de réplicas exige essa revisão. O piloto não
publica disponibilidade mensal no frontend, não retreina e não prolonga sua própria janela.
Decisões e limites: [ADR 0012](../adr/0012-piloto-coleta-externa.md) e
[ADR 0013](../adr/0013-arranque-frio-e-piloto-2.md).
