# Preparação de reservas com PySpark

## Ambiente

O ambiente recomendado para o laboratório é Docker Linux: Python 3.12, Java 21 e versões
fixadas de PySpark, pandas e Arrow. Na raiz do projeto, depois de exportar o modelo:

```powershell
docker build -t hotelml:local .
docker build -f pipelines/Dockerfile --target spark -t hotelml:spark .
```

Alternativamente, instale `requirements-spark.lock` num ambiente com Java compatível e use
`hotelml features --master 'local[2]' ...`. Não é necessário instalar Spark na imagem da API.
Ao atualizar dependências, resolva o lock opcional com o runtime como constraint:

```text
uv pip compile pyproject.toml --extra spark --constraint requirements.lock --python-version 3.12 --universal --output-file requirements-spark.lock
```

## Input e execução

O Parquet de entrada precisa de `booking_id` e todas as colunas `INPUT_COLUMNS`. O ID deve vir
do sistema de origem e manter-se estável entre execuções; nulos, strings vazias e duplicados
fazem o job falhar. O dataset público de demonstração não tem esse identificador de negócio.
Para um exemplo sintético, crie IDs apenas para esse ficheiro:

```powershell
New-Item -ItemType Directory -Force data/batch | Out-Null
python -c "from hotelml.synthetic import make_synthetic; d=make_synthetic(1000); d.insert(0,'booking_id',[f'demo-{i}' for i in range(len(d))]); d.to_parquet('data/batch/input.parquet',index=False)"
$batchDir = (Resolve-Path data/batch).Path
docker run --rm -v "${batchDir}:/data" hotelml:spark features --master 'local[2]' --input /data/input.parquet --output /data/features-v1
```

A saída contém IDs, entradas do modelo e features derivadas, sem alvo nem colunas de
vazamento. O cálculo usa a mesma função de features do sklearn. Não é preciso remover as
colunas adicionais do ficheiro bruto antes do job: apenas as contratadas são selecionadas.

O comando imprime o número de linhas e os caminhos. Por defeito, o job recusa sobrescrever
uma saída. Para repetir, escolha outro diretório, por exemplo `features-v2`. Um erro de dados
interrompe o lote inteiro. Uma falha durante a escrita pode deixar um diretório incompleto;
nunca consuma uma saída sem `_SUCCESS`.

## Testes e execução em cluster

```powershell
docker build -f pipelines/Dockerfile --target test -t hotelml:spark-test .
$testDir = (Resolve-Path tests).Path
docker run --rm -v "${testDir}:/tests:ro" hotelml:spark-test -c /app/pyproject.toml /tests/test_spark_features.py -o cache_dir=/tmp/pytest-cache
```

O CI executa os mesmos testes num container com JVM. O ambiente sem a dependência opcional
assinala esses testes como skipped; a cobertura mínima de 80% continua aplicada ao núcleo.

O exemplo Docker usa duas threads locais e `SPARK_LOCAL_IP=127.0.0.1`. Para um cluster real,
configure master, endereçamento de rede e storage partilhado segundo o ambiente, e instale o
mesmo pacote e locks nos executores. Não use o loopback da imagem local para comunicação entre
máquinas. Nesta etapa não foi provisionado um cluster Azure nem um agendamento de jobs.
