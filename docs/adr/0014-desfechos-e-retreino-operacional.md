# ADR 0014: Adaptador de desfechos e retreino candidato

- **Status:** ferramentas aceitas; política de gatilhos **proposta**, vale com a aprovação do
  responsável
- **Data:** 2026-11-15

## Contexto

O [ADR 0008](0008-avaliacao-com-desfechos.md) definiu o contrato de desfechos, mas nenhuma fonte
o produzia. O [ADR 0009](0009-exercicio-retreino.md) exercitou o retreino com dados sintéticos e
deixou em aberto gatilhos, agendamento e a comparação com o modelo de produção.

Não existe um sistema de hotel ligado a este projeto. A única fonte de resultados observados é
o próprio dataset, que traz `reservation_status` e `reservation_status_date`: as colunas
excluídas do treino por vazamento são, por definição, o desfecho de cada reserva.

## Decisão: adaptador de desfechos

`hotelml outcomes` converte uma exportação da origem (`booking_id`, `reservation_status`,
`reservation_status_date`) para o contrato do ADR 0008.

- `Canceled` e `No-Show` viram `is_canceled = 1`; `Check-Out` vira 0. É a mesma regra do alvo
  de treino: nas 119.390 linhas do dataset, os três estados coincidem com `is_canceled`.
- `resolved_at` recebe o instante declarado em `--available-at`, com fuso, e não a data do
  evento. O contrato proíbe datas retroativas que escondam o atraso de disponibilização; um
  desfecho só existe para avaliação quando a origem o exporta.
- Estados ainda abertos só são aceitos se declarados em `--pending-status`; ficam fora do
  arquivo e continuam pendentes na avaliação. Qualquer outro estado interrompe a exportação.
- Datas ausentes, inválidas ou posteriores à disponibilização, IDs repetidos ou vazios e
  colunas em falta também interrompem. Nada é gravado em caso de erro.
- Um manifesto ao lado do Parquet registra contagens por estado e os hashes da origem e do
  resultado. O hash do resultado é o mesmo que `hotelml quality` grava no seu relatório.

## Decisão: validação com dados observados

`scripts/replay_outcomes.py` pontua o período de teste temporal com o bundle, exporta os
desfechos pelo adaptador e compara as métricas de `quality` com as calculadas diretamente pelo
alvo. Em 2026-11-15, com o dataset real e o modelo versão 1:

| Verificação | Resultado |
| --- | --- |
| Reservas do período de teste (chegadas a partir de 2017-04-22) | 23.842 |
| Desfechos exportados: cancelados / mantidos | 9.739 / 14.103 |
| Cobertura de desfechos | 100% |
| Maior diferença entre as duas formas de calcular as métricas | 0,0 |
| ROC AUC pelos desfechos exportados | 0,8614 |

Os valores são idênticos aos registrados no treino, como deve ser: são as mesmas reservas e o
mesmo modelo. O replay confirma que a cadeia adaptador → avaliação está correta sobre dados
observados. **Não** mede o modelo em reservas novas, e o scoring é feito em pandas, fora do
lote Spark monitorado. Um teste automatizado repete a verificação com dados sintéticos e
inclui uma origem com estados trocados, que tem de ser detectada.

## Decisão: gatilhos de retreino

`hotelml retrain-check` lê relatórios já existentes e uma política versionada
(`monitoring/retraining-policy.json`) e grava uma recomendação. Não treina nem promove.

| Gatilho | Regra proposta |
| --- | --- |
| Drift | Sinal nos 2 relatórios de drift mais recentes; um lote isolado não basta |
| Qualidade | ROC AUC abaixo de 0,80 num relatório `ready` com desfechos `observed` |
| Idade | Mais de 180 dias desde o treino |

Relatórios sintéticos, dados insuficientes e métricas indefinidas nunca acionam. Com a política
em `proposed`, o relatório mostra os sinais e deixa `retrain_recommended` nulo; só com
`approved` o comando recomenda e devolve código 2. Os limiares são pontos de partida sem
histórico de operação: 0,80 fica seis centésimos abaixo do teste histórico (0,8614).

O gatilho de idade é o único componente de agendamento. Não há execução automática: o registry
é um SQLite local, e um workflow agendado treinaria num registry vazio, com números de versão
sem significado. A verificação é manual ou feita por quem opera a máquina do registry.

## Decisão: retreino candidato

`scripts/retrain_candidate.py` executa um retreino quando há gatilho:

1. Lê o bundle aprovado e as evidências antes de registrar qualquer coisa.
2. Treina com `promote=False`: a versão nova recebe só o alias `challenger`.
3. Reavalia o bundle aprovado no teste temporal dos dados novos, com a mesma limpeza e corte.
4. Se a ROC AUC do candidato superar a do aprovado por mais que `--min-delta`, exporta a versão
   explícita e gera `model-bundle.tar.gz` com o SHA-256 e a versão que o CD pede.
5. Grava um relatório com gatilho, hashes das evidências, métricas dos dois modelos e decisão.

O champion e a API publicada não mudam. A publicação continua a exigir uma release aprovada e
o workflow de deploy. Com o dataset real e o modelo versão 1 como aprovado, em registry
temporário, o retreino reproduziu as mesmas métricas (diferença de ROC AUC 0,0) e, corretamente,
não gerou candidato: sem dados novos não há ganho.

## Limites

- **Sem fonte viva.** O adaptador está pronto para uma exportação real, mas nenhuma chega. A
  API não registra reservas nem IDs de negócio ([ADR 0003](0003-serving-e-deploy.md)); ligar
  previsões online a desfechos exigiria decidir o que armazenar e com que base legal.
- **Comparação num único teste.** Repetir candidatos no mesmo teste inflaciona o ganho aparente.
  Se o bundle aprovado tiver visto reservas posteriores ao corte, a comparação favorece-o; o
  manifesto não guarda o corte de treino, por isso o script não consegue verificar.
- **Gatilhos não validados.** Não houve drift nem queda de qualidade observados em operação.
- **Sem agendamento automático**, pelo motivo acima.

## Consequências

A fase 4 passa a ter o ciclo completo em ferramentas testadas: desfechos, qualidade, gatilho,
candidato e pacote para o CD. O que falta não é código: uma origem real de desfechos, a
aprovação das políticas e evidência de operação para calibrar os limiares.
