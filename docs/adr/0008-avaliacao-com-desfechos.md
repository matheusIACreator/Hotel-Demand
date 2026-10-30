# ADR 0008: Qualidade offline com desfechos finais e corte temporal

- **Status:** aceito
- **Data:** 2026-10-30

`hotelml quality` avalia as previsões já produzidas por um lote monitorado concluído. Não executa
novas previsões: usa probabilidade, decisão, limiar, versão e horário gravados no scoring.
O marcador `_SUCCESS` da raiz é obrigatório. Identidade, contagem e coerência das decisões
são verificadas contra `run.json` antes de calcular métricas.

## Contrato de desfechos

Um arquivo Parquet externo fornece `booking_id` (string não vazia), `is_canceled` (inteiro 0/1 ou
booleano) e `resolved_at` (data com fuso). Esse contrato é novo, offline, e deve ser produzido
por uma fonte autorizada. Não há endpoint ou integração de hotel fornecendo esses dados ainda.

`resolved_at` representa o instante em que o sistema de origem confirmou e disponibilizou o
resultado como **final** para avaliação. Não use data retroativa de evento para ocultar atraso
de disponibilização. Não envie estados provisórios, como uma reserva ainda aberta marcada
como não cancelada. Quando a origem corrigir um resultado, gere um novo arquivo e relatório.

Cada ID aparece uma vez em cada arquivo. Repetições são rejeitadas para impedir multiplicação
de linhas no join. Desfechos de outros IDs são contados, mas não afetam as métricas. Desfechos
anteriores ao scoring são rejeitados por inconsistência temporal. O produtor deve preservar
o mesmo ID de negócio usado no lote; a ferramenta não reconstrói IDs a partir de dados pessoais.

O corte `--as-of` é explícito e deve ter fuso. Só entram previsões e resultados conhecidos até
esse instante. TimestampType do Spark sem fuso segue o contrato UTC do batch. O avaliador não
consegue verificar a veracidade da data declarada pelo produtor nem autorização da fonte.

## Relatório

O JSON inclui data UTC, corte, identidade do lote/modelo, hashes das fontes, volume elegível,
desfechos encontrados, pendências, cobertura e IDs externos não utilizados. Não inclui IDs ou
resultados individuais. `--data-kind synthetic|observed` é obrigatório e representa declaração
do operador, não comprovação automática da origem dos dados.

Por padrão são necessários 30 pares previsão/desfecho; esse mínimo é uma proteção inicial,
não uma garantia de precisão estatística. Abaixo disso, `status=insufficient_data` e métricas
nulas. Com volume suficiente, calcula acurácia, precisão, recall, F1, Brier, log loss, ROC AUC,
average precision (PR AUC) e matriz de confusão. AUCs ficam nulas com classe única; razões com
denominador zero também ficam nulas. Nenhum valor indefinido é substituído por um indicador
positivo ou por uma confiança artificial.

A cobertura parcial pode enviesar a avaliação: cancelamentos costumam ser conhecidos antes de
reservas concluídas. As métricas descrevem apenas os resultados finais disponíveis. Não são
diretamente comparáveis ao teste temporal histórico sem coortes equivalentes. Não afirmamos
que o lote amadureceu inteiro, pois a saída atual não contém data prevista de encerramento.

Esta etapa opera em memória sobre um lote local e arquivo de desfechos; não é uma avaliação
distribuída de todo o histórico. Não publica indicadores operacionais no frontend nem altera
aliases, retreina modelos ou aplica políticas automáticas de promoção.
