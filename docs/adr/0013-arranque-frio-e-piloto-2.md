# ADR 0013: Correção do arranque a frio, piloto 2 e metas propostas

- **Status:** correção aceita e publicada em 2026-11-14; piloto 2 e metas **propostos**, entram
  em vigor com a aprovação do responsável (merge desta alteração e aprovação da política)
- **Data:** 2026-11-15

## Contexto

O piloto do [ADR 0012](0012-piloto-coleta-externa.md) coletou 17 tentativas principais em 122
slots e todas falharam. A [análise](../validation/arranque-frio-2026-11-15.md) mostrou uma causa
determinística: sair de zero réplicas levava 45 a 55 s e o proxy da Vercel desistia aos 20 s.
Dos 45 a 55 s, cerca de 29 s eram a readiness probe, que exigia três sucessos com intervalo de
10 s depois de a API já estar pronta. O responsável pediu a correção e a publicação.

O ADR 0012 mandava manter os timeouts durante o piloto. Esta decisão substitui essa regra de
forma explícita, com a evidência do próprio piloto, como ele previa para a sua revisão.

## Decisão: correção

1. **Probes.** Readiness com um sucesso, intervalo e timeout de 1 s e 30 falhas toleradas.
   Startup com intervalo e timeout de 1 s e 150 falhas. As tolerâncias anteriores (30 s e 150 s)
   ficam iguais. O modelo carrega antes de a porta abrir, por isso um sucesso basta.
2. **Proxy.** `/api/predict` espera 50 s pela API e declara `maxDuration = 60`. O ingress da
   Azure retém o pedido enquanto a réplica arranca; com tempo suficiente, a primeira chamada é
   atendida sem repetição pelo cliente.
3. **Interface.** Depois de 4 s sem resposta, mostra o aviso de inicialização. A consulta a
   `/api/health` seguida de nova tentativa continua como proteção se o proxy esgotar o tempo.
4. **Sem mudança:** escala a zero, CPU, memória, imagem, modelo, alertas e orçamento.

Resultado medido em três arranques a frio: primeira chamada atendida em 30,2 a 31,1 s, com
sucesso. A espera depois de o modelo estar pronto caiu de 29 s para cerca de 5,5 s.

## Decisão proposta: piloto 2

O piloto 1 termina com esta alteração: o sistema medido mudou no slot 122 e os resultados
anteriores e posteriores não se agregam. Os slots 0 a 121 ficam como evidência do sistema
anterior. O slot 122 e os runs até 00:21 UTC de 2026-11-15 são excluídos.

O piloto 2 (`external-20261116`) mantém a política do ADR 0012, com duas diferenças:

- **Janela:** de 2026-11-16 00:17 UTC a 2026-11-30 00:17 UTC, fim exclusivo, 336 slots.
- **Timeout do coletor: 60 s** em vez de 30 s. O arranque medido (~31 s) fica acima de 30 s por
  cerca de um segundo. Com 30 s, quase toda principal viraria `timeout` sem registrar a duração
  real: o limite censuraria exatamente a grandeza que o piloto precisa medir. 60 s é o teto da
  sondagem e fica acima dos 50 s do proxy, de modo que uma desistência do proxy aparece como
  504 e não como timeout do coletor.

O limite de tráfego não muda: uma principal por hora e até dois diagnósticos após falha. Como o
gate usa a política versionada, não há tráfego entre o merge e o início da nova janela. Se o
merge ocorrer depois do início, os slots anteriores ficam como lacuna de coleta.

`scripts/probe_pilot.py review` passa a resumir os journals baixados: resultado e duração de
cada principal, diagnósticos e tempo até a recuperação. O comando não gera tráfego.

## Decisão proposta: metas

`monitoring/slo-policy.json` fixa as metas **antes** da avaliação, como exige o
[ADR 0010](0010-sli-slo-interno.md). Enquanto `status` for `proposed`, `review --slo` mostra as
taxas observadas e deixa `met` nulo. Só o responsável muda o estado para `approved`.

| Objetivo | Meta proposta | Escopo |
| --- | --- | --- |
| Primeira chamada com previsão válida | 95% das principais | piloto 2, caminho Vercel → Azure |
| Primeira chamada em até 45 s | 90% das principais | idem; falhas contam como lentas |
| Volume mínimo para concluir | 30 principais | abaixo disso, `insufficient_data` |
| Sucesso HTTP interno em `/predict` | 99% | `hotelml slo`, pedidos que chegam à API |
| Latência interna até 2.000 ms | 95% | idem; mínimo de 100 pedidos |

Os 45 s deixam margem sobre os ~31 s medidos e ficam abaixo do timeout do proxy. Os valores
internos repetem os limiares dos alertas do [ADR 0005](0005-observabilidade-api.md). São pontos
de partida escolhidos com três amostras, não compromissos demonstrados.

## Limites conhecidos

- **Cobertura.** O agendador do GitHub entregou 14% dos slots do piloto 1. Com a mesma taxa, o
  piloto 2 teria cerca de 47 principais: acima do mínimo, mas com uma falha a pesar ~2 pontos.
  A meta de 95% tolera duas falhas nesse volume. Se a cobertura cair, o resultado fica
  inconclusivo em vez de aprovado.
- **Metas internas.** O volume esperado na janela fica abaixo de 100 pedidos; a avaliação
  interna deve sair `inconclusive`. A meta fica registrada para quando houver tráfego.
- **Arranque de ~31 s.** Continua perceptível. A interface avisa, mas um cliente com timeout
  menor que isso falha na primeira chamada.

## Alternativas não adotadas

- **Manter uma réplica sempre ativa.** Elimina o arranque a frio, mas contraria a política de
  escala a zero do ADR 0012 e cria custo permanente. Decisão de orçamento do responsável.
- **Imagem de serving menor.** A imagem tem 293 MB comprimidos e o pull com a preparação do nó
  leva ~14 s. Um lock só para serving (sem servidor MLflow, Arrow e gráficos) deve reduzir esse
  tempo, mas altera dependências do modelo e exige nova validação de carregamento e previsões.
- **Mais CPU.** O arranque do Python leva ~5 s com 0,5 vCPU. Mais CPU encurta esse trecho e
  aumenta o custo por segundo ativo. Não foi medido.
- **Coletor fora do GitHub Actions.** Um job agendado na Azure daria cobertura horária real.
  Exige novo recurso, orçamento e destino para os journals. Continua sendo o caminho para uma
  coleta recorrente depois dos pilotos.
- **Manter o timeout de 30 s no piloto.** Preservaria a comparação com o piloto 1, mas essa
  comparação já não existe depois de mudar o sistema, e o custo seria perder as durações.

## Consequências

A primeira chamada depois de uma pausa passa a ser atendida, em cerca de 31 s. O piloto 1 não
produz taxa de disponibilidade utilizável: documenta a falha e a sua causa. As metas só ficam
validadas depois do piloto 2, com a política aprovada antes da avaliação.

Reverter: restaurar os valores das probes em `infra/main.tf` e aplicar; promover na Vercel o
deployment anterior. O estado Terraform continua local.
