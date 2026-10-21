# ADR 0002: Model Registry com aliases (champion / challenger)

- **Status:** aceito
- **Data:** 2026-10-21

## Contexto

O MLflow 3 recomenda aliases no lugar dos antigos "stages". Precisamos de promoção controlada e
rollback rápido.

## Decisão

- Todo treino registra uma nova versão e recebe o alias `challenger`.
- O challenger só vira `champion` se superar o champion atual em `roc_auc` no **mesmo** conjunto
  de teste (margem mínima configurável via `--min-delta`).
- Ao promover, o champion anterior recebe o alias `previous_champion`.
- **Rollback** troca `champion` e `previous_champion`: é uma operação de metadados, sem rebuild
  nem redeploy.
- Quem consome o modelo (batch e API) sempre resolve `models:/<nome>@champion`.

## Consequências

- Rollback em segundos e auditável (histórico de aliases no registry).
- O rollback é um *toggle*: executá-lo duas vezes desfaz o primeiro.
- Na fase de operação, o gatilho de retraining por drift usará o mesmo fluxo de promoção.
