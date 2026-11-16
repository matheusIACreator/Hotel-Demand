# Casos do eval da explicação de previsões

30 casos. Cada um é o JSON de fatos enviado ao modelo de linguagem.
Reservas: `make_synthetic(600, seed=11)`; modelo `hotel-cancellation` versão 1. Casos `editado` são alterações declaradas de fatos reais.

| Caso | Faixa | Prob. | Base | Decisão | Fatores | Líder | Nota |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `baixa-01` | baixa | 0.0% | 35.9% | manutenção provável | 6 | required_car_parking_spaces |  |
| `baixa-02` | baixa | 0.5% | 35.9% | manutenção provável | 6 | — |  |
| `baixa-03` | baixa | 1.4% | 35.9% | manutenção provável | 6 | — |  |
| `baixa-04` | baixa | 4.0% | 35.9% | manutenção provável | 6 | customer_type |  |
| `baixa-05` | baixa | 9.5% | 35.9% | manutenção provável | 6 | market_segment |  |
| `baixa-06` | baixa | 19.9% | 35.9% | manutenção provável | 6 | — |  |
| `media-baixa-01` | media-baixa | 20.5% | 35.9% | manutenção provável | 6 | total_of_special_requests |  |
| `media-baixa-02` | media-baixa | 25.5% | 35.9% | manutenção provável | 6 | country |  |
| `media-baixa-03` | media-baixa | 28.7% | 35.9% | manutenção provável | 6 | country |  |
| `media-baixa-04` | media-baixa | 33.9% | 35.9% | manutenção provável | 6 | — |  |
| `media-baixa-05` | media-baixa | 41.3% | 35.9% | manutenção provável | 6 | country |  |
| `media-baixa-06` | media-baixa | 49.7% | 35.9% | manutenção provável | 6 | — |  |
| `media-alta-01` | media-alta | 50.2% | 35.9% | cancelamento provável | 6 | country |  |
| `media-alta-02` | media-alta | 59.2% | 35.9% | cancelamento provável | 6 | country |  |
| `media-alta-03` | media-alta | 63.6% | 35.9% | cancelamento provável | 6 | — |  |
| `media-alta-04` | media-alta | 69.3% | 35.9% | cancelamento provável | 6 | deposit_type |  |
| `media-alta-05` | media-alta | 74.4% | 35.9% | cancelamento provável | 6 | country |  |
| `media-alta-06` | media-alta | 79.1% | 35.9% | cancelamento provável | 6 | market_segment |  |
| `alta-01` | alta | 80.6% | 35.9% | cancelamento provável | 6 | lead_time |  |
| `alta-02` | alta | 91.2% | 35.9% | cancelamento provável | 6 | deposit_type |  |
| `alta-03` | alta | 97.7% | 35.9% | cancelamento provável | 6 | previous_cancellations |  |
| `alta-04` | alta | 99.6% | 35.9% | cancelamento provável | 6 | previous_cancellations |  |
| `alta-05` | alta | 99.8% | 35.9% | cancelamento provável | 6 | deposit_type |  |
| `alta-06` | alta | 100.0% | 35.9% | cancelamento provável | 6 | — |  |
| `limite-sem-fatores` | limite | 97.7% | 35.9% | cancelamento provável | 0 | — | Nenhum fator com efeito claro. |
| `limite-um-fator` | limite | 97.7% | 35.9% | cancelamento provável | 1 | previous_cancellations | Um único fator, que é o líder. |
| `limite-no-limiar` | limite | 50.0% | 35.9% | cancelamento provável | 6 | previous_cancellations | Probabilidade exatamente no limiar. |
| `limite-abaixo-do-limiar` | limite | 49.9% | 35.9% | manutenção provável | 6 | — | Logo abaixo do limiar. |
| `limite-valor-ausente` | limite | 1.4% | 35.9% | manutenção provável | 3 | — | Fator cujo valor na reserva é nulo. |
| `limite-igual-a-base` | limite | 35.9% | 35.9% | manutenção provável | 6 | — | Estimativa igual à das reservas típicas. |

## baixa-01

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Vagas de estacionamento (`required_car_parking_spaces`) | 1 | reduz | 15.5 |
| País de origem (`country`) | DEU | reduz | 8.3 |
| Segmento de mercado (`market_segment`) | Offline TA/TO | reduz | 6.6 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 6.0 |
| Antecedência da reserva, em dias (`lead_time`) | 221 | aumenta | 3.3 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 2.8 |

## baixa-02

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| País de origem (`country`) | FRA | reduz | 9.8 |
| Segmento de mercado (`market_segment`) | Offline TA/TO | reduz | 9.6 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 8.1 |
| Diária média (`adr`) | 52.08 | reduz | 4.4 |
| Alterações na reserva (`booking_changes`) | 1 | reduz | 4.0 |
| Cancelamentos anteriores (`previous_cancellations`) | 0 | reduz | 3.5 |

## baixa-03

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 8.1 |
| Segmento de mercado (`market_segment`) | Corporate | reduz | 8.1 |
| País de origem (`country`) | BRA | reduz | 8.0 |
| Diária média (`adr`) | 52.29 | reduz | 4.6 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 4.1 |
| Cancelamentos anteriores (`previous_cancellations`) | 0 | reduz | 3.6 |

## baixa-04

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de cliente (`customer_type`) | Transient-Party | reduz | 9.4 |
| Pedidos especiais (`total_of_special_requests`) | 2 | reduz | 7.5 |
| País de origem (`country`) | IRL | reduz | 7.4 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 7.2 |
| Cancelamentos anteriores (`previous_cancellations`) | 0 | reduz | 3.6 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 2.6 |

## baixa-05

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Segmento de mercado (`market_segment`) | Direct | reduz | 12.2 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 7.4 |
| Noites durante a semana (`stays_in_week_nights`) | 0 | reduz | 6.0 |
| País de origem (`country`) | ESP | reduz | 4.6 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 4.6 |
| Cancelamentos anteriores (`previous_cancellations`) | 0 | reduz | 3.5 |

## baixa-06

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Antecedência da reserva, em dias (`lead_time`) | 11 | reduz | 11.3 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 10.6 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 7.5 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 6.3 |
| Semana do ano da chegada (`arrival_date_week_number`) | 3 | aumenta | 4.7 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 3.9 |

## media-baixa-01

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 12.1 |
| País de origem (`country`) | FRA | reduz | 9.7 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 6.7 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 6.4 |
| Diária média (`adr`) | 160.61 | aumenta | 6.4 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 3.3 |

## media-baixa-02

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| País de origem (`country`) | FRA | reduz | 15.0 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 8.1 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 7.4 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 5.9 |
| Semana do ano da chegada (`arrival_date_week_number`) | 37 | reduz | 4.5 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 3.1 |

## media-baixa-03

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| País de origem (`country`) | PRT | aumenta | 15.8 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 11.2 |
| Tipo de cliente (`customer_type`) | Transient-Party | reduz | 9.3 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 4.7 |
| Semana do ano da chegada (`arrival_date_week_number`) | 28 | reduz | 4.5 |
| Antecedência da reserva, em dias (`lead_time`) | 93 | aumenta | 3.3 |

## media-baixa-04

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 12.3 |
| País de origem (`country`) | PRT | aumenta | 12.1 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 5.4 |
| Semana do ano da chegada (`arrival_date_week_number`) | 22 | reduz | 3.7 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 3.5 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 3.1 |

## media-baixa-05

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| País de origem (`country`) | FRA | reduz | 11.4 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 9.6 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 8.8 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 5.7 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 3.9 |
| Diária média (`adr`) | 81.22 | reduz | 3.8 |

## media-baixa-06

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 10.9 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 10.6 |
| Diária média (`adr`) | 140.14 | aumenta | 6.6 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 5.4 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 4.9 |
| Antecedência da reserva, em dias (`lead_time`) | 69 | aumenta | 3.9 |

## media-alta-01

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| País de origem (`country`) | PRT | aumenta | 20.0 |
| Antecedência da reserva, em dias (`lead_time`) | 368 | aumenta | 13.0 |
| Pedidos especiais (`total_of_special_requests`) | 2 | reduz | 11.5 |
| Semana do ano da chegada (`arrival_date_week_number`) | 46 | aumenta | 6.9 |
| Segmento de mercado (`market_segment`) | Offline TA/TO | reduz | 6.8 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 4.7 |

## media-alta-02

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| País de origem (`country`) | PRT | aumenta | 13.9 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 8.7 |
| Diária média (`adr`) | 73.4 | reduz | 4.6 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 4.3 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 4.0 |
| Antecedência da reserva, em dias (`lead_time`) | 29 | aumenta | 3.4 |

## media-alta-03

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Antecedência da reserva, em dias (`lead_time`) | 256 | aumenta | 13.8 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 13.5 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 12.4 |
| Semana do ano da chegada (`arrival_date_week_number`) | 33 | reduz | 6.3 |
| País de origem (`country`) | ITA | reduz | 5.8 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 5.6 |

## media-alta-04

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | Non Refund | aumenta | 60.6 |
| Tipo de cliente (`customer_type`) | Transient-Party | reduz | 15.9 |
| País de origem (`country`) | FRA | reduz | 4.6 |
| Segmento de mercado (`market_segment`) | Offline TA/TO | reduz | 4.2 |
| Hotel (`hotel`) | Resort Hotel | reduz | 3.9 |
| Dia de chegada (`arrival_date_day_of_month`) | 2 | reduz | 3.5 |

## media-alta-05

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| País de origem (`country`) | PRT | aumenta | 23.1 |
| Antecedência da reserva, em dias (`lead_time`) | 323 | aumenta | 13.0 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 11.9 |
| Segmento de mercado (`market_segment`) | Groups | reduz | 10.5 |
| Diária média (`adr`) | 129.98 | aumenta | 4.1 |
| Semana do ano da chegada (`arrival_date_week_number`) | 25 | reduz | 3.7 |

## media-alta-06

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 14.6 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 11.9 |
| Diária média (`adr`) | 141.46 | aumenta | 9.5 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 6.5 |
| Antecedência da reserva, em dias (`lead_time`) | 52 | aumenta | 5.0 |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 4.2 |

## alta-01

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Antecedência da reserva, em dias (`lead_time`) | 128 | aumenta | 11.6 |
| País de origem (`country`) | PRT | aumenta | 8.9 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 8.6 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 4.6 |
| Segmento de mercado (`market_segment`) | Online TA | aumenta | 4.4 |
| Semana do ano da chegada (`arrival_date_week_number`) | 5 | aumenta | 3.9 |

## alta-02

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | Non Refund | aumenta | 64.4 |
| Tipo de cliente (`customer_type`) | Transient-Party | reduz | 11.7 |
| Segmento de mercado (`market_segment`) | Groups | reduz | 6.3 |
| Semana do ano da chegada (`arrival_date_week_number`) | 44 | aumenta | 4.5 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 4.3 |
| Diária média (`adr`) | 143.91 | aumenta | 3.4 |

## alta-03

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Cancelamentos anteriores (`previous_cancellations`) | 1 | aumenta | 65.8 |
| Segmento de mercado (`market_segment`) | Offline TA/TO | reduz | 8.3 |
| País de origem (`country`) | GBR | reduz | 5.4 |
| Antecedência da reserva, em dias (`lead_time`) | 50 | aumenta | 3.1 |
| Vagas de estacionamento (`required_car_parking_spaces`) | 0 | aumenta | 3.0 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 2.6 |

## alta-04

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Cancelamentos anteriores (`previous_cancellations`) | 1 | aumenta | 41.6 |
| País de origem (`country`) | PRT | aumenta | 6.2 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 4.0 |
| Vagas de estacionamento (`required_car_parking_spaces`) | 0 | aumenta | 3.7 |
| Diária média (`adr`) | 126.68 | aumenta | 2.6 |
| Antecedência da reserva, em dias (`lead_time`) | 36 | aumenta | 2.3 |

## alta-05

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | Non Refund | aumenta | 59.8 |
| País de origem (`country`) | PRT | aumenta | 8.9 |
| Segmento de mercado (`market_segment`) | Offline TA/TO | reduz | 4.6 |
| Dias em lista de espera (`days_in_waiting_list`) | 26 | reduz | 4.5 |
| Diária média (`adr`) | 20.0 | reduz | 3.1 |
| Tipo de cliente (`customer_type`) | Transient | aumenta | 2.7 |

## alta-06

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | Non Refund | aumenta | 29.7 |
| Cancelamentos anteriores (`previous_cancellations`) | 1 | aumenta | 26.7 |
| País de origem (`country`) | PRT | aumenta | 5.0 |
| Segmento de mercado (`market_segment`) | Groups | reduz | 4.1 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 2.6 |
| Antecedência da reserva, em dias (`lead_time`) | 120 | aumenta | 2.3 |

## limite-sem-fatores

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| (nenhum fator) | | | |

## limite-um-fator

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Cancelamentos anteriores (`previous_cancellations`) | 1 | aumenta | 65.8 |

## limite-no-limiar

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Cancelamentos anteriores (`previous_cancellations`) | 1 | aumenta | 65.8 |
| Segmento de mercado (`market_segment`) | Offline TA/TO | reduz | 8.3 |
| País de origem (`country`) | GBR | reduz | 5.4 |
| Antecedência da reserva, em dias (`lead_time`) | 50 | aumenta | 3.1 |
| Vagas de estacionamento (`required_car_parking_spaces`) | 0 | aumenta | 3.0 |
| Pedidos especiais (`total_of_special_requests`) | 0 | aumenta | 2.6 |

## limite-abaixo-do-limiar

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 8.1 |
| Segmento de mercado (`market_segment`) | Corporate | reduz | 8.1 |
| País de origem (`country`) | BRA | reduz | 8.0 |
| Diária média (`adr`) | 52.29 | reduz | 4.6 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 4.1 |
| Cancelamentos anteriores (`previous_cancellations`) | 0 | reduz | 3.6 |

## limite-valor-ausente

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 8.1 |
| Segmento de mercado (`market_segment`) | Corporate | reduz | 8.1 |
| Empresa (`company`) | None | reduz | 2.4 |

## limite-igual-a-base

| Campo | Valor | Sentido | Efeito (p.p.) |
| --- | --- | --- | --- |
| Tipo de depósito (`deposit_type`) | No Deposit | reduz | 8.1 |
| Segmento de mercado (`market_segment`) | Corporate | reduz | 8.1 |
| País de origem (`country`) | BRA | reduz | 8.0 |
| Diária média (`adr`) | 52.29 | reduz | 4.6 |
| Pedidos especiais (`total_of_special_requests`) | 1 | reduz | 4.1 |
| Cancelamentos anteriores (`previous_cancellations`) | 0 | reduz | 3.6 |
