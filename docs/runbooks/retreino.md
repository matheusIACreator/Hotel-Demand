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
