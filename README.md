# hotelml: plataforma MLOps de referência

Previsão de cancelamento de reservas de hotel, usada como pretexto para construir e documentar o
ciclo completo de ML em produção: dados, treino reprodutível, registry, serving, monitoramento,
alertas e operação, com infraestrutura em código na Azure.

## Estado atual: API publicada e pipelines Spark validados

| Fase | Conteúdo | Estado |
|---|---|---|
| 1 | Pacote, testes, CI, treino com MLflow, registry champion/challenger | **feito** |
| 2 | API FastAPI em container + Terraform na Azure + CD | API publicada e validada; configuração do CD pendente |
| 3 | Feature pipeline e batch scoring em PySpark | implementada e validada localmente |
| 4 | Monitoramento (drift, qualidade), alertas, SLOs, runbooks, retraining | pendente |
| 5 | LLMOps com Anthropic: tracing, evals, prompts versionados, guardrails, custo | pendente |
| 6 | Post-mortem simulado, template reutilizável, diagrama de arquitetura | pendente |

## Início rápido

```bash
python -m venv .venv && source .venv/bin/activate
make install

make check              # ruff + mypy + pytest
make train-synthetic    # treino local com dados sintéticos
make train-real         # baixa o dataset do Hugging Face e treina
make status             # versões champion / challenger / previous_champion
make rollback           # volta o champion para a versão anterior
make mlflow-ui          # http://localhost:5000
```

Copie `.env.example` para `.env` e preencha só o que precisar. O `.env` nunca é versionado.
CLI e API carregam esse ficheiro sem sobrescrever variáveis já definidas no ambiente.

No Windows/PowerShell, os comandos equivalentes estão no
[runbook de deploy](docs/runbooks/deploy-azure.md). As dependências estão fixadas em
`requirements.lock` (runtime) e `requirements-dev.lock` (desenvolvimento/CI).

## API e publicação

```bash
hotelml export --output model-bundle
uvicorn hotelml.api:app --host 127.0.0.1 --port 8000
# Swagger: http://127.0.0.1:8000/docs
docker build -t hotelml:local .
docker run --rm -p 8001:8000 hotelml:local
```

`POST /predict` aceita `{"bookings": [...]}` com 1 a 100 reservas no contrato `INPUT_COLUMNS`.
A resposta inclui nome/versão do modelo, probabilidade de cancelamento e decisão (limiar 0,5).
`GET /health/live` e `GET /health/ready` são usados pelas probes e smoke tests.

A API local resolve o champion no arranque; com `MODEL_BUNDLE`, usa o snapshot exportado.
O container contém o modelo e não depende do registry durante a inferência. Alterações de aliases
exigem reinício ou novo deploy; consulte o [ADR 0003](docs/adr/0003-serving-e-deploy.md) e o
[runbook de rollback](docs/runbooks/rollback.md).

`infra/` cria Container Apps (0–1 réplicas), ACR, identidade com `AcrPull`, logs e orçamento.
O workflow manual **Deploy Azure** usa OIDC, CI obrigatório, smoke tests e deploy por digest.
O primeiro deploy pode ser local; o CD requer um MLflow remoto com champion acessível ao runner.
O exemplo tem ingress público de demonstração. Configuração, limitações e controlo de custos:
[runbook de deploy](docs/runbooks/deploy-azure.md).

## Como funciona o treino

1. `validate_raw` confere o contrato dos dados (falha cedo, listando todos os problemas).
2. `clean_training_data` remove linhas inválidas e cria a data de chegada.
3. `time_split` treina no passado e avalia no futuro.
4. O pipeline (features, pré-processamento, estimador) é logado no MLflow com assinatura, exemplo
   de entrada e uma amostra de referência (base do detector de drift).
5. O modelo é registrado como `challenger` e só vira `champion` se superar o atual
   (ver `docs/adr/0002-registry-por-aliases.md`).

## Interface web

`web/` contém a interface em Next.js, TypeScript, Tailwind e shadcn/ui: visão geral com o estado
real da API, simulador de cancelamento integrado a `/predict`, métricas históricas do modelo,
pipeline em lote e arquitetura. O navegador fala apenas com rotas de servidor do Next.js, que
chamam a API definida em `HOTELML_API_URL` e tratam a inicialização a frio da Container App.
O schema do formulário é comparado com o OpenAPI exportado da FastAPI, e as métricas exibidas
vêm do run MLflow. Comandos, testes e deploy na Vercel: [web/README.md](web/README.md).

## Pipelines de dados

`hotelml features --input <parquet> --output <novo-diretório> --master 'local[2]'` prepara
reservas com PySpark. A origem exige `booking_id` único e `INPUT_COLUMNS`; o job reutiliza a
validação e as features da API, preservando os IDs e excluindo alvo/colunas de vazamento.
Spark e Java são opcionais e têm um container próprio. Comandos e testes no
[runbook de pipelines](docs/runbooks/pipelines-spark.md).

A preparação foi executada pela CLI sobre 200 reservas sintéticas, produzindo Parquet com
200 IDs únicos e 33 colunas. A integração Spark compara as features com o pipeline sklearn e
testa a rejeição de IDs inválidos, dados fora do contrato e sobrescrita de saídas.

`hotelml batch --input <parquet> --output <novo-diretório> --bundle <snapshot> --master 'local[2]'`
calcula previsões com o pipeline completo. O snapshot é distribuído aos executores Spark,
carregado uma vez por partição e identificado em cada previsão. A saída contém ID, probabilidade,
decisão, nome/versão do modelo, limiar, identificação do lote e horário UTC.

Os testes de integração Spark verificam a paridade das features e previsões com sklearn,
a preservação dos IDs, a reutilização do modelo entre lotes Arrow e as saídas sem sobrescrita.
Não foi provisionado um cluster nem um agendamento de jobs na Azure.

## Estrutura

```
src/hotelml/   config, data, schema, features, train, metrics, registry, cli, synthetic
tests/         unitários e de integração (MLflow em SQLite temporário)
docs/adr/      decisões de arquitetura
infra/         Terraform Azure (fase 2)
scripts/       smoke test da API local e publicada
pipelines/     jobs Spark (fase 3)
web/           interface Next.js (simulador, modelo, arquitetura)
```

## Decisões e pendências

- Dataset sem licença declarada na cópia do Hugging Face: ver ADR 0001. Os dados não são versionados.
- CI e testes usam dados sintéticos com o mesmo schema, então rodam sem rede.

## Treino real validado em 2026-10-21

O download e o treino do dataset `gemuchu/hotel_bookings` foram executados localmente:
119.390 linhas brutas, 95.366 reservas no treino e 23.842 no teste, com corte em 2017-04-22.
O HistGradientBoosting foi registado como versão 1 no registry local e exportado para serving.

| Métrica no teste temporal | Valor |
| --- | --- |
| ROC AUC | 0,8614 |
| PR AUC (average precision) | 0,8234 |
| F1 | 0,6936 |
| Accuracy | 0,7779 |
| Brier | 0,1569 |
| Log loss | 0,4638 |

Um smoke test HTTP com esse bundle confirmou readiness e três previsões válidas, incluindo
a versão do modelo na resposta. Estes resultados descrevem este dataset e esta divisão;
não medem desempenho em tráfego de produção.

Em 2026-10-22, a imagem Docker Linux foi construída e validada com esse modelo: readiness e
três previsões HTTP passaram, o processo executou com UID 10001 e a imagem não contém `.env`
nem a base SQLite local. O container de teste foi encerrado após a validação.

Validação da implementação: 43 testes do núcleo passaram, com 94,79% de cobertura, e 20 testes
de integração Spark passaram no container. O módulo Spark opcional é validado separadamente
e não entra nessa percentagem de cobertura. Ruff, formatação, mypy e Terraform passaram;
o GitHub Actions também executou com sucesso o CI, incluindo os testes Spark e o smoke Docker.

## Deploy Azure validado em 2026-10-22

A API foi publicada em North Europe pelo Terraform, com o modelo versão 1 e imagem do ACR
fixada por digest. O smoke test HTTPS confirmou readiness e três previsões válidas:
[documentação interativa da API](https://api-hotelml-dev.mangoplant-1a4839a2.northeurope.azurecontainerapps.io/docs).

O grupo de recursos mantém os metadados em West Europe; os serviços ficam em North Europe,
pois a Azure recusou novos recursos em West Europe para esta subscrição. O ambiente usa
Consumption, com 0–1 réplicas, identidade `AcrPull` e alertas de orçamento a 50%, 80% e 100%.
O orçamento mensal é 20 na moeda da subscrição e não interrompe os recursos.

O deploy foi realizado localmente. O workflow de CD continua dependente da configuração
da identidade OIDC, das variáveis do GitHub e de um registry MLflow remoto acessível ao runner;
consulte o [runbook](docs/runbooks/deploy-azure.md).
