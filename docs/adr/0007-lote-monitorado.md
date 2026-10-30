# ADR 0007: Drift amostrado junto do scoring distribuído

- **Status:** aceito
- **Data:** 2026-10-30

`hotelml reference` baixa `reference/reference.parquet` do run explícito no manifesto do bundle.
Grava um pacote separado, com nome, versão, run e SHA-256. O pacote contém dados de treino e
deve ter acesso controlado; não é incluído automaticamente na imagem ou na release do serving.
O bundle e o pacote são artefatos confiáveis: hash detecta alterações acidentais, não autentica
um manifesto adulterado junto com o conteúdo.

`hotelml batch-monitor` é opt-in; `hotelml batch` mantém o comportamento anterior. A nova
execução verifica a identidade e integridade da referência e compara as entradas antes do
scoring, reutilizando os métodos e limiares do ADR 0006. Referência de outra versão/run falha.

A entrada deve ser um Parquet imutável durante a execução. É persistida no Spark para diagnóstico
e scoring. Só uma amostra de até 5.000 linhas chega ao driver, escolhida pelos menores xxhash64
de `booking_id`, com desempate pelo ID. Todos os IDs são únicos e válidos. A seleção é estável
para os mesmos IDs; o hash não garante representatividade. A referência também precisa caber
no limite configurado. Ambos os lados exigem 200 linhas por padrão; dados insuficientes impedem
uma execução monitorada, em vez de produzir um falso diagnóstico de ausência de drift.

O drift usa entradas cruas, sem o alvo. A validação completa dos valores ocorre no scoring,
inclusive fora da amostra. Mudança acima do limiar apenas sinaliza investigação: a execução
continua, sem retreino ou promoção automática.

A saída é um diretório local novo, acessível ao driver, com `scores/` (Parquet), `drift.json`,
`run.json` e `_SUCCESS`. Previsões e relatório compartilham `batch_id` e identidade do modelo.
Somente o marcador da raiz confirma a conclusão conjunta; o `_SUCCESS` interno do Spark não
basta. Falhas de escrita podem deixar saída parcial, que deve ser investigada e não consumida.
Não há sobrescrita. Use um novo diretório para repetir.

Esta etapa não agenda jobs cloud nem publica indicadores no frontend. Janelas reais exigem
origem autorizada, seleção temporal e referência do modelo correspondente. A avaliação de drift
permanece amostral; o scoring continua distribuído sobre todas as reservas.
