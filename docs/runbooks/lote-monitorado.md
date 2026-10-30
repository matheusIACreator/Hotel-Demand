# Executar drift e scoring no mesmo lote

Requer a imagem Spark atualizada ou Python com `requirements-spark.lock` e Java compatível.
Consulte o runbook de pipelines para construir o ambiente. Os comandos abaixo são para CLI
Python/PowerShell; em container, monte os caminhos de entrada, pacote e saída no driver.

## Preparar referência da versão aprovada

```powershell
hotelml reference --bundle model-bundle --output data/reference-v1
```

O MLflow configurado precisa disponibilizar o run descrito em `model-bundle/manifest.json`.
O comando não resolve aliases nem treina modelos. A saída contém `reference.parquet` e manifesto
com o hash e a identidade exata. Esse pacote é separado do bundle e contém reservas de treino;
controle acesso e proveniência/licença e não publique seus dados em releases públicas.

## Processar

```powershell
hotelml batch-monitor --input data/batch/input.parquet --output data/batch/run-001 --bundle model-bundle --reference data/reference-v1 --master 'local[2]'
```

Entrada: `booking_id` string, único e não vazio, e todas as `INPUT_COLUMNS`. Use um Parquet
imutável. O destino precisa ser novo e local ao driver; essa interface não grava metadados
diretamente em um URI de storage cloud.

O comando retorna 0 quando drift e scoring concluem, mesmo com `drift_detected=true`. Erros de
dados, integridade, tamanho mínimo ou processamento impedem a conclusão. Ao contrário do comando
isolado `hotelml drift`, o código 2 não é usado para sinalizar drift nesse fluxo.

Confira `_SUCCESS` na raiz, `run.json` e `drift.json`. Compare `batch_id`, nome/versão/run e hash
da referência. Os Parquets em `scores/` preservam IDs, probabilidades, limiar e identificação
do lote. Ausência do marcador da raiz significa resultado incompleto, mesmo que `scores/`
tenha seu próprio `_SUCCESS`. Não consuma saídas parciais; investigue e repita em outro destino.

## Amostragem e limites

Por padrão, o driver recebe até 5.000 reservas; o mínimo é 200. Ajuste `--sample-rows`,
`--minimum-rows`, `--psi-threshold`, `--tv-threshold` e `--threshold` conscientemente. O limite
também deve comportar a referência, que não é truncada silenciosamente. Um ID estável dá uma
seleção reproduzível, não uma garantia estatística de representatividade.

Para amostras insuficientes, use o batch convencional se o scoring for necessário, registrando
que o drift não foi avaliado. Não confunda ausência de avaliação com ausência de drift.

## Validar com dados sintéticos

Os testes Spark `test_monitored_batch_preserves_predictions_and_drift` executam dois lotes:
um igual à referência sintética e outro com antecedência deslocada em 1.000 dias. Ambos produzem
previsões e relatório, com igualdade das probabilidades em relação ao pipeline sklearn.
Outro teste insere uma reserva inválida fora da amostra e exige falha antes do marcador final.

```powershell
docker run --rm -v "${PWD}/tests:/tests:ro" hotelml:spark-test -c /app/pyproject.toml /tests/test_spark.py -k monitored -o cache_dir=/tmp/pytest-cache
```

O CI executa esses cenários com os demais testes Spark. Para receber dados reais, defina origem
autorizada e janelas comparáveis; não use logs da API para reconstruir reservas. Um sinal de
drift pede investigação, não retreino ou bloqueio automáticos.
