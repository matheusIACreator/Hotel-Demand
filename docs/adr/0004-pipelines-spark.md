# ADR 0004: Features e scoring distribuídos com o contrato partilhado

- **Status:** aceito
- **Data:** 2026-10-22

## Contexto

A fase 3 precisa de preparar reservas em lote sem mover o dataset inteiro para a memória do
driver e sem criar outra implementação das features usadas no treino e na API.

## Decisão

- PySpark é uma dependência opcional, fixada em `requirements-spark.lock`. A imagem da API
  permanece sem JVM e sem Spark. `pipelines/Dockerfile` acrescenta Spark e Java 21.
- O input é Parquet com as colunas de inferência e `booking_id`, uma string não vazia e única
  fornecida pelo sistema de origem. Não geramos IDs a partir da ordem das partições.
- O job rejeita lote vazio, IDs inválidos/duplicados e reservas fora do contrato. Não elimina
  silenciosamente reservas inválidas nem reutiliza a filtragem exclusiva do treino.
- `mapInPandas` processa lotes Arrow, limitados por defeito a 1000 linhas. Cada reserva passa
  pelo mesmo `Booking` da API e as features vêm da função partilhada `add_features`.
- A saída preserva o ID, as colunas de inferência e as features derivadas. Alvo, colunas de
  vazamento e outras colunas extras da origem são excluídos.
- A escrita usa `errorifexists`: cada execução recebe um diretório novo. O job materializa e
  valida os lotes antes de escrever. O consumidor só deve aceitar saídas com `_SUCCESS`.
- O scoring recebe um bundle exportado, sem consultar aliases nos executores. O driver verifica
  o snapshot e distribui um ZIP via `SparkContext.addArchive`. O ZIP permanece na área gerida
  pelo Spark até ao fim da sessão, para suportar a execução lazy e novas tentativas das tarefas.
- Cada partição carrega o mesmo snapshot uma vez, reutilizando-o nos lotes Arrow. O pipeline
  sklearn completo recebe as colunas brutas; features previamente calculadas são recalculadas
  pelo modelo para preservar a paridade com a API e evitar entradas derivadas desatualizadas.
- As previsões incluem `booking_id`, probabilidade, decisão, nome/versão do modelo, limiar,
  `batch_id` e `scored_at` em UTC. Probabilidades inválidas interrompem o lote.

## Consequências

As dependências do treino e do serving ficam preservadas pelo lock de runtime, usado como
constraint ao resolver Spark. Testes de integração executam a JVM e comparam as features do
Spark com as do pipeline, incluindo valores ausentes e várias partições/lotes Arrow.

A cobertura do núcleo exclui apenas o módulo opcional `hotelml.spark`; os testes Spark rodam
separadamente no container com Java. A limitação de 1000 linhas aplica-se aos lotes Arrow,
não ao tamanho total da entrada. A validação de unicidade exige shuffle global dos IDs.

API e executores partilham `bundle.load_bundle`. Um snapshot não muda após a troca de aliases;
para usar outra versão, exporte outro bundle. Os arquivos distribuídos ocupam disco até ao
fim da sessão: os comandos CLI encerram o Spark num bloco `finally`. Sessões permanentes
precisam de uma política de ciclo de vida dos snapshots antes de muitos jobs consecutivos.

## Referências

- [mapInPandas](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.DataFrame.mapInPandas.html)
- [Instalação do PySpark](https://spark.apache.org/docs/latest/api/python/getting_started/install.html)
- [Distribuição de arquivos](https://spark.apache.org/docs/latest/api/python/reference/api/pyspark.SparkContext.addArchive.html)
