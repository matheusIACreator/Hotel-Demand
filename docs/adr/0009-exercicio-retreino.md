# ADR 0009: Exercício local de retreino e decisão de promoção

- **Status:** aceito
- **Data:** 2026-11-08

## Contexto

O treino e o registry já permitem registrar um challenger sem promovê-lo e reavaliar o champion
no mesmo teste temporal do candidato. Faltava um exercício reproduzível que demonstrasse esse
fluxo completo, incluindo rejeição, seleção do snapshot e inferência após a decisão.

## Decisão

`scripts/exercise_retraining.py` usa somente dados sintéticos e um registry SQLite temporário.
Um modelo inicial aprende com uma janela histórica menor; o retreino utiliza a janela acumulada,
com mais reservas. As datas de chegada são substituídas por dias consecutivos para garantir que
nenhuma data do treino alcance o teste final. O histórico inicial também termina antes desse
teste. Isso demonstra separação temporal, sem simular disponibilização real de desfechos.

O challenger é registrado com `promote=False`. Primeiro, um ganho mínimo de 1 em ROC AUC
demonstra que a promoção é bloqueada e preserva o champion. Depois, o ganho mínimo normal de
zero decide com os scores medidos, sem forçar uma promoção. O champion é reavaliado no teste
do retreino; sua métrica histórica não entra nessa comparação.

O exercício exporta o champion selecionado, verifica readiness e uma previsão HTTP local.
Também verifica que o snapshot anterior mantém as previsões e, se houver promoção, que
`previous_champion` aponta para a versão anterior. Um relatório agregado registra métricas,
decisões, IDs dos runs, versões, limites temporais e SHA-256 dos bytes Parquet gerados.

## Limites e consequências

O relatório é criado em destino novo e os artefatos temporários são removidos. IDs dos runs e
hash do dataset identificam o ensaio, mas não permitem recuperar os modelos após a limpeza;
o Parquet e seu hash podem variar entre versões das dependências. O script restaura as URIs
globais do MLflow, inclusive em caso de falha, e recusa execução dentro de um run ativo.

Este exercício não estabelece gatilhos operacionais, agendamento, fonte autorizada de desfechos
ou critérios estatísticos de aceitação. Drift ou um relatório `quality` isolado não iniciam
retreino. Em produção, a janela deve conter apenas resultados finais disponíveis no corte;
uma melhoria no teste não equivale a aprovação de release. Promoção no registry não altera
a API publicada: bundle, revisão e smoke test continuam seguindo o CD existente.
