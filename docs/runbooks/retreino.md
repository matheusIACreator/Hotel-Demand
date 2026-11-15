# Ensaiar retreino e seleção de modelo localmente

## Execução

Com as dependências de desenvolvimento instaladas, execute na raiz do projeto:

```powershell
.venv/Scripts/python scripts/exercise_retraining.py --output data/reports/retraining-001.json
```

Escolha um destino novo a cada execução. Não é necessário configurar `.env`, baixar dados ou
acessar a Azure. O script configura explicitamente seu próprio registry, nome de modelo,
experimento e diretório de artefatos temporários. Não execute dentro de um run MLflow ativo.

## Evidências esperadas

Confira no JSON:

1. `scope=synthetic_local_temporary_registry` e `trigger=manual_exercise`.
2. `train_end < test_start`, histórico menor que o treino acumulado e contagens de treino/teste.
3. Scores de baseline e candidato no mesmo teste em `metrics_on_retraining_test`.
4. `blocked_decision.promoted=false`: o ganho mínimo artificial de 1 impediu a promoção.
5. `decision`: com ganho mínimo zero, promoção ocorre somente se a ROC AUC do candidato superar
   a do baseline. Uma rejeição nessa etapa é resultado válido.
6. `selected_version`, `previous_snapshot_preserved`, `readiness_passed` e `prediction_passed`.

O baseline usa regularização forte para tornar o exemplo instrutivo, mas a promoção depende
dos resultados calculados. Datas e métricas do ensaio não representam tráfego ou melhoria real.
Um erro de validação impede a gravação de um relatório de sucesso. Registry e bundles são
removidos ao terminar, inclusive na falha; somente o relatório agregado permanece.

## Verificar os gatilhos

`hotelml retrain-check` transforma relatórios existentes numa recomendação. Não treina.

```powershell
hotelml retrain-check --trained-at '2026-10-21T21:51:18Z' --drift data/batch/run-001/drift.json --drift data/batch/run-002/drift.json --quality data/reports/quality-001.json --output data/reports/retrain-check-001.json
```

A política está em `monitoring/retraining-policy.json`: drift nos 2 relatórios mais recentes,
ROC AUC observada abaixo de 0,80 ou modelo com mais de 180 dias. Relatórios sintéticos e com
dados insuficientes não acionam; o motivo aparece em `notes`. Use `--as-of` para fixar o
instante da avaliação ao reproduzir uma decisão.

Enquanto a política estiver em `proposed`, o relatório lista os sinais e deixa
`retrain_recommended` nulo. O responsável aprova mudando `status` para `approved`. A partir
daí o código 2 significa "retreino recomendado". Não há agendamento automático: o registry é
local, então a verificação é feita por quem o opera, por exemplo a cada lote monitorado.

## Retreino candidato

Com um gatilho, treine um candidato contra o bundle aprovado em produção:

```powershell
.venv/Scripts/python scripts/retrain_candidate.py --source data/novas-reservas.parquet --baseline-bundle model-bundle --trigger drift --evidence data/reports/retrain-check-001.json --output data/reports/retrain-candidate-001
```

1. `report.json`: confira `test_cutoff`, linhas de treino e teste, e as métricas dos dois
   modelos no **mesmo** teste. `candidate_better` só é verdadeiro se a ROC AUC superar a do
   aprovado por mais que `--min-delta`.
2. Sem ganho, só o relatório é gravado. A versão nova fica no registry como `challenger`.
3. Com ganho, o diretório traz `candidate-bundle/` e `model-bundle.tar.gz`; `release` informa
   `model_sha256` e `model_version` para o workflow **Deploy Azure**.
4. `approval: pending_human_review`: o script não promove nem publica. Revise coortes, classes
   e o corte antes de criar a release, e siga o [runbook de deploy](deploy-azure.md).

O champion e a API não mudam em nenhum caso. Se o bundle aprovado foi treinado com reservas
posteriores ao corte do novo teste, a comparação favorece-o; o manifesto não permite verificar
isso automaticamente. Em 2026-11-15, o retreino com o mesmo dataset reproduziu as métricas da
versão 1 e não gerou candidato. Decisões: [ADR 0014](../adr/0014-desfechos-e-retreino-operacional.md).

## Retreino com dados observados

Antes de usar o fluxo existente com uma fonte real, documente a origem autorizada, o corte de
disponibilização dos desfechos, a janela de treino e um teste futuro sem sobreposição. O
contrato de [qualidade](qualidade-desfechos.md) fornece resultados finais de avaliação; seu
relatório agregado não contém as features necessárias para treinar um modelo.

Registre o candidato com `hotelml train --source <arquivo> --no-promote` e preserve os dados,
artefatos e parâmetros usados. Revise cobertura, classes e métricas em coortes equivalentes.
Não use a comparação repetida de muitos candidatos no mesmo teste como garantia de melhoria.
O exercício não fornece aprovação automática nem agendamento para dados observados.

Após uma decisão de promoção aprovada no processo operacional, siga o
[runbook de deploy](deploy-azure.md) para exportar e publicar o bundle e o de
[rollback](rollback.md) para recuperação. Alterar somente o alias não atualiza a API.

## Teste automatizado

```powershell
.venv/Scripts/python -m pytest tests/test_retraining_exercise.py
```

O teste executa treinos e inferência reais em ambiente temporário, confere o bloqueio,
a coerência da seleção com as métricas, a separação temporal, a restauração das URIs e
a rejeição de sobrescrita. Decisão e limites: [ADR 0009](../adr/0009-exercicio-retreino.md).
