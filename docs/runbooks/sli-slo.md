# Medir SLIs internos e avaliar objetivos

## Escopo

Este relatório mede sucesso HTTP e latência **dentro do processo** em `POST /predict`. Não é
disponibilidade de ponta a ponta. Mantenha esse escopo ao compartilhar os resultados. Escala a
zero, ausência de eventos e um P95 baixo não comprovam que o serviço esteve acessível.
Para medir do lado do cliente, use a [sondagem externa finita](sondagem-externa.md). Seus
resultados têm outro escopo e denominador e não devem ser misturados com estes eventos internos.

## Exportar eventos observados

A [consulta KQL](../queries/slo-events.kql) exporta eventos sem conteúdo de reservas. O filtro
de aplicação está fixado para o laboratório `api-hotelml-dev`; ajuste-o ao ambiente desejado.
Execute com uma identidade que já tenha acesso de leitura ao workspace. Não é necessário
alterar recursos, gerar tráfego ou ativar sondagens para exportar logs existentes.

Exemplo PowerShell para avaliar o dia 1 de novembro de 2026 e incluir ingestão posterior:

```powershell
New-Item -ItemType Directory -Force data/reports | Out-Null
$destination = 'data/reports/slo-events-001.json'
if (Test-Path -LiteralPath $destination) { throw 'Escolha um destino novo' }
$workspace = az monitor log-analytics workspace show -g rg-hotelml-dev -n logs-hotelml-dev --query customerId -o tsv
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível consultar o workspace' }
$query = Get-Content docs/queries/slo-events.kql -Raw
$exportEnd = [DateTimeOffset]::UtcNow.ToString('o')
@{ query = $query; timespan = "2026-11-01T00:00:00Z/$exportEnd" } | ConvertTo-Json | Set-Content data/reports/slo-query-001.json -Encoding utf8
$raw = az rest --method POST --url "https://api.loganalytics.azure.com/v1/workspaces/$workspace/query" --resource 'https://api.loganalytics.io' --body '@data/reports/slo-query-001.json' -o json
if ($LASTEXITCODE -ne 0) { throw 'Exportação falhou; não avalie uma saída parcial' }
$raw | Set-Content -LiteralPath $destination -Encoding utf8
```

`timespan` filtra o horário de ingestão do workspace. O avaliador filtra o `timestamp` do
evento na janela solicitada. Estenda a consulta para incluir atrasos de ingestão; reexporte
depois de aguardar a ingestão se necessário. Preserve os arquivos usados em cada avaliação.
Um resultado HTTP bem-sucedido da consulta não comprova completude: confira erros parciais,
limites de resultados, retenção, cota, falhas de coleta e cobertura de todas as revisões.
Exports sobrepostos não devem ser concatenados sem controle; IDs duplicados são rejeitados.

## Linha de base e objetivos propostos

As metas abaixo são **exemplos**, não valores de produção aprovados. Defina os limites e a
janela antes da análise. O primeiro comando deixa a completude sem confirmação:

```powershell
.venv/Scripts/python -m hotelml.cli slo --input data/reports/slo-events-001.json --input-format azure --output data/reports/slo-baseline-001.json --start '2026-11-01T00:00:00Z' --end '2026-11-02T00:00:00Z' --data-kind observed --availability-target 0.99 --latency-target 0.95 --latency-ms 2000
```

Confira `eligible_requests`, `excluded_client_errors`, os SLIs e `successful_latency_ms`.
Volume baixo ou coleta não confirmada tornam a avaliação inconclusiva. O mínimo padrão de
100 pedidos é uma proteção de volume, não garantia de precisão estatística. Não o reduza
apenas para obter um resultado positivo. Para ensaios locais, declare `--data-kind synthetic`.

Após verificar a coleta da janela, gere **outro relatório** com `--complete-window`. Essa flag
registra sua declaração; a ferramenta não valida a integridade do sistema de observação.
Para logs locais, a entrada padrão é JSONL: um objeto de telemetria por linha, sem prefixos
de logger. `--input-format azure` aceita o JSON REST bruto do exemplo, não CSV nem o formato
tabular de outros comandos Azure.

## Interpretar e agir

1. `status=inconclusive`: não há conclusão de cumprimento; `met` e orçamento ficam nulos.
2. `status=ready`: confira os dois objetivos. Latência usa a proporção de pedidos que foram
   bem-sucedidos **e** rápidos sobre todos os elegíveis; falhas rápidas não contam como boas.
3. `remaining_bad_requests < 0` ou `burn_rate > 1`: orçamento consumido além do permitido nessa
   janela. Orçamento fracionário não autoriza arredondar para uma falha extra.
4. Investigue alterações de revisão, startup e erros com o [runbook de monitoramento](monitoramento-api.md).
   Revise também os 4xx, excluídos dos SLIs: erros de contrato e limitação de taxa afetam clientes.
5. Havendo regressão ligada a uma publicação, siga [rollback](rollback.md). Não retreine por
   lentidão ou indisponibilidade sem investigar a causa; qualidade do modelo tem outro contrato.

O comando retorna 2 quando algum objetivo avaliável é violado. Retorna 0 para objetivos
cumpridos **ou** resultado inconclusivo: automações devem verificar `status`. Não publique
indicadores no frontend apenas porque o comando terminou sem erro.

## Validação

`python -m pytest tests/test_slo.py` usa telemetria sintética: taxas e orçamentos conhecidos,
falhas rápidas, ausência de tráfego, cortes temporais, classe de eventos, duplicação, contratos,
resposta Azure parcial, proveniência e CLI. Esses testes não medem o serviço publicado.
Definições e limites: [ADR 0010](../adr/0010-sli-slo-interno.md).

Na consulta de leitura de 2026-11-08, o workspace retornou zero eventos elegíveis de ingestão
desde 2026-11-01 até 17:20 UTC. O relatório local `data/reports/slo-baseline-20261108.json`
ficou `inconclusive`, sem valores de SLI nem orçamento. Não se confirmou completude da coleta;
o resultado não demonstra indisponibilidade nem permite aprovar as metas dos exemplos.
