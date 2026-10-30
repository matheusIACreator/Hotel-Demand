# Avaliar previsões após conhecer o resultado das reservas

## Antes de executar

Use um lote de `hotelml batch-monitor` com `_SUCCESS` na raiz. Conserve seus artefatos imutáveis.
Peça à fonte autorizada um Parquet com:

| Campo | Conteúdo |
| --- | --- |
| `booking_id` | Mesmo ID string da reserva no lote, único e não vazio |
| `is_canceled` | Resultado final: inteiro 0/1 ou booleano, sem nulos |
| `resolved_at` | Instante de confirmação/disponibilização do resultado final, com fuso |

Não trate reservas abertas como não canceladas. Não preencha desfechos ausentes nem reconstrua
IDs com informações pessoais. A coleta real depende do sistema de origem; os logs da API não
contêm os dados necessários para esse vínculo. Valide autorização, retenção e os significados
dos campos com o produtor antes de usar dados observados.

## Comando

```powershell
hotelml quality --batch data/batch/run-001 --outcomes data/outcomes.parquet --as-of '2026-10-30T12:00:00Z' --data-kind observed --output data/reports/quality-001.json
```

Escolha um corte real e um novo destino. Para ensaios, use `--data-kind synthetic`.
`--minimum-rows` tem padrão 30. O comando retorna 0 ao gerar um relatório, inclusive quando há
dados insuficientes; consulte sempre `status` e `outcome_coverage`, não apenas o código de saída.
Erros de contrato, identidade e integridade impedem o relatório. Arquivos existentes nunca
são sobrescritos. Se houver correção ou mais desfechos, use outro destino.

## Interpretar

1. Confira o lote, versão/run do modelo, corte temporal e `data_kind`.
2. Veja previsões elegíveis, resultados finais disponíveis e pendências. Cobertura parcial não
   demonstra maturidade da coorte; taxas de cancelamento podem estar enviesadas nessa fase.
3. Com `status=insufficient_data`, aguarde mais resultados. Métrica nula não significa zero.
4. Com dados suficientes, confira classes e matriz de confusão antes das métricas. AUCs com
   classe única ficam nulas; Brier e log loss continuam definidos.
5. Compare somente coortes equivalentes. Drift pode ajudar a investigar mudanças, mas não
   prova a causa de uma diferença de qualidade. Uma investigação não dispara retreino automático.

Hashes de `run.json`, partes Parquet e desfechos permitem identificar os bytes usados. Os
artefatos são confiáveis; hashes não são assinatura e não validam a veracidade dos desfechos.
O relatório agregado pode ser compartilhado conforme política do projeto; preserve o controle
de acesso dos arquivos com reservas e resultados individuais.

## Validação sintética

`tests/test_quality.py` cobre matriz de confusão e métricas conhecidas, cobertura parcial,
corte temporal, ausência de desfechos, classe única, dados inconsistentes, proveniência e CLI.
Execute com `pytest tests/test_quality.py`. Esses resultados validam o software e não medem
qualidade em operação real. Fonte autorizada, janelas de maturidade e periodicidade devem ser
definidas antes de alimentar indicadores de produção.
