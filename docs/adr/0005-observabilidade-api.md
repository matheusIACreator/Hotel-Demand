# ADR 0005: Telemetria da API e alertas com escala a zero

- **Status:** aceito
- **Data:** 2026-10-25

## Decisão

A API escreve eventos JSON de esquema 1 no stdout, aproveitando o workspace Log Analytics já
usado pelo Container Apps. Não é necessário adicionar SDK nem serviço de tracing nesta etapa.

- `http_request`: identificador gerado no servidor, rota controlada, método, status, duração,
  nome/versão do modelo, quantidade de reservas e classe de erro, quando disponível.
- `model_loading`, `model_ready`, `model_load_failed`, `model_stopped`: ciclo do modelo;
  `model_ready` inclui o tempo de carregamento.
- Nunca registrar corpo, probabilidades, cabeçalhos, query strings, IPs ou mensagem/traceback de
  exceções. O access log do Uvicorn é desativado porque inclui URLs fornecidas pelo cliente.
- Probes bem-sucedidas não geram eventos HTTP. Probes com falha continuam visíveis.
- `X-Request-ID` é gerado por pedido e devolvido na resposta; IDs recebidos não são reutilizados.

Três regras Terraform consultam o workspace a cada cinco minutos, em janela de 15 minutos:

| Regra | Condição inicial |
| --- | --- |
| Erros | POST /predict com pelo menos 20 pedidos, três 5xx e taxa de 5xx de 10% ou mais, por revisão |
| Latência | Pelo menos 20 previsões 2xx e P95 acima de 2.000 ms, por revisão |
| Inicialização | Evento `model_load_failed` na janela |

O grupo de ações usa o email de operação já informado em `budget_email`. Os alertas são
opt-in (`monitoring_enabled`), pois regras e ingestão podem ter custos. O laboratório ativa os
três, com resolução automática. Os limiares são configuráveis e devem ser ajustados com dados.

## Limitações e consequências

Estes limites são iniciais, não SLOs demonstrados. A duração começa quando o pedido chega ao
processo e termina no envio da resposta; exclui espera no ingress por uma réplica, trânsito de
rede e proxy Next.js. O evento de carregamento também exclui agendamento e download da imagem.

Ausência de pedidos não significa falha: a API escala para zero. Os alertas de tráfego ficam
sem sinal quando não há volume suficiente. Não fazemos sondagens externas periódicas nesta
etapa para evitar manter a réplica acordada. Falhas antes de iniciar o Python (por exemplo,
pull da imagem) exigem consultar os logs de sistema e o resultado do CD.

As consultas usam `TimeGenerated` do workspace. Atraso de ingestão ou a cota diária de logs pode
atrasar ou impedir alertas; não há garantia de detecção em cinco minutos. Métricas históricas
de teste, drift e qualidade do modelo são assuntos separados. Nenhum agregado é publicado
no frontend sem uma fonte consultável e autorização apropriada.

## Referências

- [Logs de Container Apps](https://learn.microsoft.com/azure/container-apps/log-monitoring)
- [Regras de alerta de logs](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-create-log-alert-rule)
