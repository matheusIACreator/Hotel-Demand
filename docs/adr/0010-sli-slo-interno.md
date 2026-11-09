# ADR 0010: SLIs internos e avaliação explícita de objetivos

- **Status:** aceito
- **Data:** 2026-11-08

## Contexto

Os alertas de quinze minutos detectam sintomas com limites iniciais, mas não estabelecem SLOs.
A telemetria existente observa apenas pedidos que chegaram ao processo da API. Não cobre
falhas anteriores ao Python, espera por réplica, trânsito de rede ou o caminho pela Vercel.

## Decisão

`hotelml slo` avalia uma janela UTC semiaberta `[start, end)` de eventos `http_request` de
`POST /predict`. Aceita JSONL ou a resposta REST do Log Analytics com uma tabela de uma coluna
`event_json` string. Rejeita erros parciais explícitos da resposta Azure, IDs repetidos dentro
da janela, telemetria incompatível e durações/status inválidos. O avaliador opera em memória
sobre exportações locais; não é um serviço de monitoramento contínuo.
O `timestamp` é emitido no fim do processamento: a atribuição à janela segue esse instante,
e pedidos ainda em andamento no corte não aparecem como concluídos.

Pedidos 4xx são excluídos do denominador e contados separadamente. Todos os demais status
válidos entram no denominador, e somente 2xx são sucessos. Esse indicador mede sucesso HTTP
dos pedidos observados elegíveis, não a correção semântica da previsão. A classificação de 4xx,
incluindo 429, é explícita: estes erros exigem investigação própria e não ficam invisíveis.

O objetivo de latência conta sucessos 2xx com duração menor ou igual ao limite, divididos por
todos os pedidos elegíveis. Assim uma falha rápida também consome o orçamento de latência.
P50/P95/P99 são calculados separadamente, somente entre 2xx, usando interpolação linear NumPy.
Esses percentis podem diferir do estimador aproximado usado no KQL dos alertas.

As duas metas e o limite de duração são obrigatórios, sem valores normativos embutidos. Metas
devem estar estritamente entre zero e um. Com `N` pedidos e meta `T`, o orçamento permitido é
`N * (1 - T)` pedidos ruins; o restante pode ficar negativo. Consumo e burn rate equivalem a
`ruins / (N * (1 - T))` nesta janela única. Não há arredondamento para conceder uma falha nem
extrapolação para pedidos ou dias futuros; isso não é um alerta de burn rate em múltiplas janelas.

Sem declaração explícita de coleta completa ou com volume menor que o mínimo (padrão 100), o
relatório é `inconclusive`: taxas observadas continuam disponíveis, mas cumprimento e orçamento
ficam nulos. Janela sem tráfego não é sucesso. Completude é declaração do operador, não prova
automática de ausência de perdas, duplicação fora da exportação ou eventos censurados.

O relatório registra janela, metas, escopo, origem declarada (`synthetic|observed`), hash dos
bytes de entrada e agregados, sem IDs individuais. Nunca sobrescreve relatórios. Código 2 indica
objetivo violado com dados avaliáveis; 0 também pode representar janela inconclusiva e exige
inspeção de `status`. Falhas de contrato impedem o relatório.

## Consequências

O mecanismo permite coletar uma linha de base e avaliar objetivos propostos sem inventar
medidas operacionais. Os exemplos do runbook não são compromisso de disponibilidade nem metas
validadas de produção. Uma política operacional deve fixar janela, volume, metas e responsáveis
antes da avaliação, evitando escolher limites após observar os resultados.

Não altera alertas Terraform, escala, frontend, registry ou deploy. Definir um SLO externo
continua exigindo coleta do lado do cliente ou sondagens com periodicidade e orçamento próprios;
os logs internos não podem reconstruir pedidos que nunca chegaram à aplicação.
