# ADR 0006: Drift offline e exercício isolado de rollback

- **Status:** aceito
- **Data:** 2026-10-30

## Drift

O comando `hotelml drift` compara duas amostras Parquet validadas pelo contrato `Booking`.
Seleciona apenas `INPUT_COLUMNS`; não usa alvo nem colunas posteriores ao cancelamento.
Requer 200 linhas por amostra por padrão. Não remove silenciosamente reservas inválidas.

- Entradas numéricas: PSI, com cortes nos quantis 0 a 100% da referência a cada 10%, caudas
  abertas e um bin próprio para nulos. Cortes repetidos são removidos. Referência constante
  tem bin próprio, com caudas em ambos os lados; referência totalmente nula continua comparável.
  Adiciona-se 1e-6 às proporções e normaliza-se novamente para evitar logaritmos de zero.
- Entradas categóricas, incluindo mês: distância de variação total, metade da soma das
  diferenças absolutas entre frequências. Nulos são separados e categorias novas são incluídas.
- Limiares iniciais: PSI >= 0,2 e variação total >= 0,1. São heurísticas configuráveis,
  não p-valores nem limites calibrados para produção. Um sinal em qualquer coluna sinaliza o lote.
- O JSON contém data UTC, hashes SHA-256 dos bytes comparados, contagens, método, score,
  limiar e taxas de ausência por coluna. Não contém reservas, categorias ou previsões individuais.
- Código de saída 0: sem sinal; 2: drift detectado. Erros de dados impedem gerar relatório.
  Relatórios existentes nunca são sobrescritos.

O comando opera em memória: use amostras/janelas com tamanho adequado e identifique a referência
pelo run do modelo em sua operação. O treino já salva `reference/reference.parquet` no MLflow.
A API não persiste reservas: dados atuais precisam ser fornecidos por uma fonte autorizada.

Mudança das entradas não demonstra perda de qualidade nem mudança da relação com o alvo.
Sazonalidade, amostras pequenas e múltiplas comparações podem gerar sinais. Calibre limiares e
janelas antes de automatizar decisões. IDs de agente/empresa são comparados como entradas cruas;
mudanças neles podem não alterar as features binárias consumidas pelo modelo. Não há retreino,
promoção, alerta cloud ou endpoint novo ligado automaticamente a esse relatório.

## Rollback

`scripts/exercise_rollback.py` cria um SQLite e artefatos temporários, treina duas versões com
dados sintéticos, promove manualmente uma candidata e restaura a anterior. O motivo é uma
decisão preventiva simulada; não afirmamos que a candidata perdeu qualidade.

O exercício usa HTTP local em memória (`TestClient`) e bundles reais: comprova que trocar o
alias não altera um processo carregado, que o novo snapshot muda a versão servida e que o
snapshot restaurado reproduz exatamente as probabilidades anteriores. Verifica readiness e
hashes dos bundles. Restaura as URIs MLflow do processo e remove o ambiente temporário.

O relatório é evidência local, não um incidente nem RTO medido na Azure. O exercício não acessa
o registry habitual nem troca imagens, tráfego ou aliases do ambiente publicado. O rollback
Azure por digest continua descrito no runbook e exige uma validação própria.
