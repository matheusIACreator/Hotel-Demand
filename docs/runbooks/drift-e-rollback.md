# Drift offline e exercício de recuperação

## Comparar uma janela

Obtenha `reference/reference.parquet` do run que originou o modelo em avaliação. Preserve o run ID
e a versão no registro operacional; não use uma referência de outro modelo sem justificar.
Prepare uma janela atual autorizada em Parquet com as entradas do contrato. A API não grava
reservas nos logs e eles não são uma fonte para reconstruí-las.

```powershell
hotelml drift --reference data/reference.parquet --current data/current.parquet --output data/reports/drift-001.json
# $LASTEXITCODE: 0 sem sinal; 2 drift. Em erro, o relatório não é produzido.
```

Limiares e volume mínimo podem ser ajustados com `--psi-threshold`, `--tv-threshold` e
`--minimum-rows`. Não reduza o mínimo apenas para obter um resultado em tráfego insuficiente.
Leia o ADR 0006 para interpretar scores, nulos, categorias novas e limitações de amostragem.

Ao detectar drift, verifique qualidade da ingestão, período, mistura de hotéis e sazonalidade.
Compare janelas equivalentes. Só proponha retreino após avaliar dados e, quando disponíveis,
desfechos reais. Uma proposta deve passar pela avaliação temporal e promoção já existentes.

## Demonstração reproduzível sem dados reais

```powershell
python -c "from hotelml.synthetic import make_synthetic; from hotelml.config import INPUT_COLUMNS; from pathlib import Path; Path('data/drift-demo').mkdir(parents=True, exist_ok=True); d=make_synthetic(2000)[INPUT_COLUMNS]; d.to_parquet('data/drift-demo/reference.parquet',index=False); d.to_parquet('data/drift-demo/same.parquet',index=False); d.assign(lead_time=d.lead_time+1000).to_parquet('data/drift-demo/shifted.parquet',index=False)"
hotelml drift --reference data/drift-demo/reference.parquet --current data/drift-demo/same.parquet --output data/drift-demo/same.json
hotelml drift --reference data/drift-demo/reference.parquet --current data/drift-demo/shifted.parquet --output data/drift-demo/shifted.json
```

O segundo comando de comparação deve sair com código 2: isso é o resultado esperado, não uma
falha de execução. Os dados são sintéticos; o deslocamento de antecedência é deliberado.

## Exercitar rollback sem alterar produção

```powershell
python scripts/exercise_rollback.py --output data/reports/rollback-exercise-001.json
```

Requer dependências de desenvolvimento (incluindo `httpx` para TestClient). O exercício cria e
remove um registry temporário, sem usar `.env` para escolher seus destinos. Não precisa de Azure,
Docker ou rede. A candidata é promovida manualmente apenas para exercitar a recuperação.

O JSON registra as versões observadas, hashes dos bundles, readiness, igualdade exata das
probabilidades restauradas e duração local. Não trate essa duração como RTO de produção.
Escolha outro destino para repetir: o comando recusa sobrescrever relatórios.

Para recuperação real, siga [rollback Azure](rollback.md): escolha um digest conhecido, valide
o endpoint e registre impacto e tempos observados. Trocar aliases sozinho não atualiza serving.
