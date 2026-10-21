# ADR 0001: Dataset, split temporal e prevenção de vazamento

- **Status:** aceito
- **Data:** 2026-10-21

## Contexto

O caso tabular prevê cancelamento de reservas de hotel (`is_canceled`). Usamos o dataset
`gemuchu/hotel_bookings` do Hugging Face (119.390 linhas, 32 colunas), uma cópia do conjunto
público "Hotel Booking Demand".

## Decisões

1. **Colunas removidas por vazamento:** `reservation_status`, `reservation_status_date` e
   `assigned_room_type`. As duas primeiras codificam o próprio desfecho; a terceira só é conhecida
   no check-in. O contrato de entrada do modelo (`INPUT_COLUMNS`) contém apenas o que existe no
   momento da reserva. Há um teste garantindo isso.
2. **Split temporal** (treino no passado, teste no futuro) em vez de aleatório. Reflete a operação
   real e já prepara a demonstração de drift.
3. **Feature engineering dentro do pipeline.** O modelo registrado aceita o payload cru, então
   treino e serving não divergem.
4. **Linhas inválidas** (zero hóspedes, `adr` negativo ou acima de 1000) são removidas só no treino.

## Licença e proveniência (pendência)

O README da cópia no Hugging Face **não declara licença**. O conjunto original foi publicado como
artigo de dados com licença aberta, mas isso deve ser confirmado na fonte original antes de
redistribuir os dados. Por precaução, o repositório **não versiona o dataset**: ele é baixado em
tempo de execução (`data/` está no `.gitignore`).

## Consequências

- Métricas mais conservadoras que as de tutoriais com split aleatório.
- CI e testes usam dados sintéticos com o mesmo schema (`hotelml.synthetic`), sem dependência de rede.
