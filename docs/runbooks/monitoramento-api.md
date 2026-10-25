# Monitoramento e diagnóstico da API

## Fonte e ativação

Eventos JSON de `hotelml.observability` chegam a `ContainerAppConsoleLogs_CL`, campo `Log_s`,
no workspace `logs-hotelml-dev`. Em `infra/terraform.tfvars`, habilite
`monitoring_enabled = true`, revise `terraform plan` e aplique o plano salvo.

São criadas três regras e um grupo de ações. Emails usam `budget_email`. O plano não altera
a escala a zero nem a imagem da API (gerenciada pelo CD). Alertas, retenção de 30 dias e cota
diária de 0,1 GB devem ser acompanhados no orçamento; atingir a cota prejudica a observação.

Após a publicação da imagem instrumentada, faça uma previsão sintética e aguarde a ingestão.
Não provoque falhas nem envie dados de clientes para testar os alertas em produção.

## Consultas

Consulte as regras exatas com `terraform -chdir=infra output -json monitoring_queries`.
No portal, selecione uma janela de 15 minutos. Pela CLI, use o customer ID do workspace:

```powershell
$workspace = az monitor log-analytics workspace show -g rg-hotelml-dev -n logs-hotelml-dev --query customerId -o tsv
$query = "ContainerAppConsoleLogs_CL | where ContainerAppName_s == 'api-hotelml-dev' | extend t=parse_json(Log_s) | where toint(t.schema_version) == 1 | project TimeGenerated, RevisionName_s, t | order by TimeGenerated desc | take 50"
az monitor log-analytics query --workspace $workspace --analytics-query $query --timespan PT1H
```

Evite imprimir tokens ou reservas no terminal durante o diagnóstico. Para investigar um pedido,
filtre `t.request_id` pelo `X-Request-ID` retornado pela API. Em clientes que usam um proxy,
o cabeçalho precisa ser repassado pelo proxy para ficar disponível ao usuário final.

## Ao receber um alerta

1. Confira regra, horário, revisão e volume. Um alerta pode se referir a uma revisão anterior
   ainda presente na janela de 15 minutos.
2. Compare com o último CD e com `/health/ready`. Erros 422 indicam entradas inválidas e não
   contam como 5xx, mas entram no volume total do alerta de erros.
3. Para falha de inicialização, procure `model_load_failed` e a classe do erro; consulte também
   `ContainerAppSystemLogs_CL` e o status da revisão para falhas anteriores ao Python.
4. Para lentidão, compare P95 e volume por revisão. A duração não mede a espera por uma réplica.
   Meça a experiência externa separadamente, identificando chamadas de inicialização a frio.
5. Se a nova imagem estiver defeituosa, siga [rollback](rollback.md), faça o smoke test e registre
   digests, versão, impacto e recuperação. Não troque somente o alias no registry.

Sem pedidos, as regras de erros e latência não disparam. Isso não comprova disponibilidade.
Sem linhas recentes após pedidos conhecidos, confira ingestão, cota e erros da regra.

## Validação dos alertas

Valide as consultas no workspace com dados sintéticos via `datatable`/`range`: tráfego saudável
deve retornar zero linhas; erros suficientes, lentidão e falha de inicialização devem retornar
linhas; baixo volume deve continuar silencioso. Esses testes não inserem dados no workspace.

O teste de notificação do grupo de ações valida somente o canal de email e envia uma mensagem
de teste. Ele não comprova que ocorreu um incidente nem que a regra detectou tráfego real.
Não marque a entrega do email como confirmada sem confirmação do destinatário.

Na validação de 2026-10-25, os nove cenários KQL passaram e as três regras foram criadas,
mas a API de teste do grupo de ações retornou `Conflict: Free subscription not supported`.
Isso impede confirmar o envio pelo mecanismo de teste nessa assinatura. O grupo de ações
permanece configurado; a entrega ao destinatário continua sem confirmação. Não interprete a
criação do recurso como evidência de recebimento de email.

## Próximos passos

Coletar uma linha de base antes de definir SLOs; medir o caminho Vercel/ingress separadamente;
avaliar sondagens com orçamento explícito; depois acrescentar drift e avaliação com desfechos
reais. O frontend continua mostrando apenas os indicadores já alimentados por fontes reais.
