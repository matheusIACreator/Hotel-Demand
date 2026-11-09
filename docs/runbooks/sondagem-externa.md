# Medir o caminho externo com inferência sintética

## Preparação e orçamento

Use a sondagem para um diagnóstico finito. Cada tentativa envia uma reserva sintética e pode
acordar a Container App, consumir inferência e gerar logs. O padrão de três chamadas com cinco
segundos entre conclusões é uma amostra curta, não um monitor de disponibilidade.

Não execute em loop ou num cron sem definir frequência, duração, localização e orçamento.
Falhas do coletor e execuções ausentes também precisam ser observadas num monitor recorrente.
Para validar o código sem tráfego, use `python -m pytest tests/test_probe.py`.

## Comandos

Na raiz do projeto, escolha diretórios novos para cada execução:

```powershell
# Caminho externo pela Vercel, incluindo o proxy Next.js e a API Azure.
.venv/Scripts/python -m hotelml.cli probe --url https://hotelml.vercel.app --target web --output data/reports/probe-web-001 --count 3 --interval 5 --timeout 30 --expected-version 1

# Acesso direto à API para diagnóstico; não passa pela Vercel.
.venv/Scripts/python -m hotelml.cli probe --url https://api-hotelml-dev.mangoplant-1a4839a2.northeurope.azurecontainerapps.io --target azure --output data/reports/probe-azure-001 --count 1 --timeout 30 --expected-version 1
```

Substitua `--expected-version` pela versão da release que pretende verificar. Omitir a flag
aceita qualquer versão preenchida; não compara o modelo publicado com o registry local.
Configure a origem sem caminhos ou parâmetros. Redirects contam como falha: use a URL final
do ambiente. HTTP só é permitido para `localhost`, `127.0.0.1` ou `::1`.

O timeout é de operações de socket, não um prazo global para DNS e todo o download. O limite
de corpo é 64 KiB. Não há repetição automática, readiness anterior nem exclusão de falhas
das estatísticas. Interrompa normalmente se necessário; preserve o diretório parcial para
diagnóstico e use outro destino ao reexecutar.

## Interpretar

1. Exija `_SUCCESS` antes de interpretar `summary.json`. Sem ele, houve coleta parcial.
2. Confira origem, alvo, versão esperada, quantidade planejada/concluída e timestamps.
3. Veja `success_rate` e `outcomes` antes dos percentis. Todas as tentativas falhadas contam,
   inclusive 4xx. Uma resposta 2xx pode falhar por previsão inválida ou versão divergente.
4. Consulte `attempts.jsonl` para a sequência e duração de cada tentativa. Primeira tentativa
   lenta não comprova cold start. Não remova essa tentativa para apresentar um percentil melhor.
5. Compare sinais do proxy e da API com os [logs internos](monitoramento-api.md). Não subtraia
   percentis de execuções diferentes para atribuir tempo à Vercel: tráfego, réplica e horário
   podem ter mudado entre elas.

`http_error` preserva somente o status. `timeout` indica timeout reportado pelo transporte;
`network_error` inclui DNS, TLS, conexão ou protocolo. `invalid_response`, `response_too_large`
e `version_mismatch` ajudam a distinguir resposta HTTP de inferência válida. Mensagens de
exceção, reservas, probabilidades e corpos não são salvos.

`_SUCCESS` confirma somente coleta completa. Código de saída 2 indica alguma tentativa
falhada, mesmo com `_SUCCESS`; zero indica sucesso de todas. `slo_status=not_evaluated` significa
que não há conclusão de SLO: a amostra curta não estabelece disponibilidade de produção nem
frequência de cold starts. A medição vem deste cliente HTTP, sem navegador ou renderização.

## Próxima janela operacional

Antes de adotar sondagens recorrentes, fixe objetivo, frequência, região do coletor, timeout,
orçamento e a política para execuções ausentes. Mantenha falhas do monitor distinguíveis de
falhas do serviço e preserve os pedidos iniciais na avaliação. A origem autorizada de desfechos
de reservas e o retreino operacional são frentes distintas desta medição de disponibilidade.

Decisões: [ADR 0011](../adr/0011-sondagem-externa-finita.md). Os SLIs internos e suas diferenças
de denominador estão no [runbook de SLIs/SLOs](sli-slo.md).

O [ensaio de 2026-11-08](../validation/sondagem-2026-11-08.md) registrou dois 504 pelo caminho
da Vercel antes de uma previsão válida. Os logs internos da janela mostraram inicialização
do modelo e somente status 200, demonstrando por que ambas as perspectivas são necessárias.
