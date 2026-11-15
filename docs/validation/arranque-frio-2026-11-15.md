# Falhas do piloto externo e correção do arranque a frio (2026-11-15)

## Pergunta

O piloto de disponibilidade ([ADR 0012](../adr/0012-piloto-coleta-externa.md)) marcou falha em
todas as tentativas principais coletadas. Este documento registra a causa, a correção aplicada e
as medições antes e depois. Decisões: [ADR 0013](../adr/0013-arranque-frio-e-piloto-2.md).

## O que o piloto registrou

Consulta ao histórico público do GitHub Actions em 2026-11-14, 23:20 UTC, slots 0 a 121:

| Observação | Valor |
| --- | --- |
| Slots horários decorridos | 122 |
| Slots com tentativa principal coletada | 17 |
| Tentativas principais bem-sucedidas | 0 |
| Cobertura de coleta | 14% |

Os dois runs concluídos sem erro não enviaram tráfego: um é anterior à janela e o outro não
tinha slot elegível. São dois problemas diferentes. As 17 falhas vêm do serviço; a cobertura de
14% vem do agendador do GitHub, que criou um run a cada 5 a 8 horas em vez de um por hora.

## Causa das falhas

O journal do slot 21 (2026-11-10), o único inspecionado em detalhe:

| Tentativa | Início (UTC) | Resultado | Duração |
| --- | --- | --- | --- |
| Principal | 18:41:00,3 | HTTP 504 | 20,9 s |
| Diagnóstico 1 | 18:41:26,2 | HTTP 200, versão 1 | 19,0 s |
| Diagnóstico 2 | 18:41:50,2 | HTTP 200, versão 1 | 0,5 s |

A principal recebe 504 aos ~21 s: é o proxy `/api/predict` da Vercel a desistir, com o seu
timeout de 20 s. O primeiro pedido atendido só termina 44,9 s depois do início da principal.
O mesmo padrão já aparecia no [ensaio de 2026-11-08](sondagem-2026-11-08.md).

Os logs do workspace para o slot 120 (2026-11-14) mostram onde o tempo é gasto. Horários de
ingestão (`TimeGenerated`), com precisão de cerca de um segundo:

| Evento | Horário (UTC) | Desde o anterior |
| --- | --- | --- |
| Escala de 0 para 1 e réplica atribuída | 21:29:04,1 | — |
| Imagem puxada | 21:29:19,0 | 14,9 s |
| Container iniciado | 21:29:24,0 | 5,0 s |
| Modelo pronto e Uvicorn a escutar | 21:29:29,8 | 5,8 s |
| Primeiros pedidos atendidos | 21:29:58,8 | **29,0 s** |

A API ficou pronta e passou 29 s sem receber o pedido que a acordou. A readiness probe estava
declarada com intervalo de 10 s e sem `success_count_threshold`; o provider `azurerm` usa 3 por
omissão. Eram precisos três sucessos seguidos, isto é, 20 a 30 s, para o ingress libertar o
tráfego. O `terraform plan` confirmou o valor em vigor (`success_count_threshold = 3 -> 1`).

Como a réplica volta a zero cinco minutos depois do último pedido e o piloto chama uma vez por
hora, toda tentativa principal encontrava zero réplicas: um arranque de 45 a 55 s contra um
proxy que espera 20 s. A falha era determinística, não intermitente.

A interface web não mostrava este erro aos usuários: depois do 504, o navegador consulta
`/api/health` e repete a previsão. O piloto mede uma única chamada, sem repetição, e por isso
registrava a falha que a interface contornava.

## Correção aplicada

| Componente | Antes | Depois |
| --- | --- | --- |
| Readiness probe | intervalo 10 s, 3 sucessos, timeout 3 s | intervalo 1 s, 1 sucesso, timeout 1 s |
| Startup probe | intervalo 5 s, 30 falhas, timeout 3 s | intervalo 1 s, 150 falhas, timeout 1 s |
| Proxy `/api/predict` | desiste aos 20 s | espera 50 s; `maxDuration` de 60 s |
| Interface | "Calculando…" até a resposta | avisa da inicialização após 4 s |

As tolerâncias a falha foram preservadas: 150 s no arranque e 30 s na readiness. Escala a zero,
CPU, memória, imagem e modelo não mudaram. O modelo carrega antes de a porta abrir, por isso um
único sucesso de readiness já significa que a API pode atender.

Publicação em 2026-11-14 (UTC): revisão `api-hotelml-dev--0000003` às 23:43 e
`api-hotelml-dev--0000004` às 23:55, ambas com a imagem
`sha256:d4bbf505…44a731` da revisão anterior; frontend em produção às 23:56
(`dpl_3Btfp6MjvivP7RTobFt3tt3EGFaM`), promovido a partir do build da branch
`fix/arranque-frio-e-fase4`.

## Medições depois da correção

Cada medição é uma chamada `hotelml probe` com reserva sintética, timeout de 60 s e a revisão
confirmada em `ScaledToZero` antes do envio. Sem readiness anterior, aquecimento ou repetição.

| Medição | Caminho | Início (UTC) | Primeira chamada | Chamada seguinte |
| --- | --- | --- | --- | --- |
| 1 | proxy novo local → Azure (revisão 3) | 14/11 23:52:10 | 200 em 30,7 s | 0,2 s |
| 2 | Vercel produção → Azure (revisão 4) | 15/11 00:02:39 | 200 em 31,1 s | 1,3 s |
| 3 | Vercel produção → Azure (revisão 4) | 15/11 00:11:33 | 200 em 30,2 s | — |

As três primeiras chamadas tiveram sucesso. Antes da correção, a mesma chamada falhava aos 20 s e
o serviço só respondia 45 a 55 s depois do primeiro pedido.

Linha do tempo da medição 2, com os horários declarados pela API para os eventos do modelo:

| Evento | Horário (UTC) | Desde o anterior |
| --- | --- | --- |
| Pedido enviado pelo cliente | 00:02:39,5 | — |
| Escala de 0 para 1 e réplica atribuída | 00:02:42,0 | 2,5 s |
| Imagem puxada | 00:02:56,1 | 14,0 s |
| Container iniciado | 00:03:00,9 | 4,8 s |
| Modelo pronto | 00:03:05,6 | 4,7 s |
| Pedido atendido | 00:03:11,1 | **5,5 s** |

A espera depois de o modelo estar pronto caiu de 29 s para cerca de 5,5 s. Passar as probes de
2–3 s para 1 s (revisão 3 para 4) não trouxe ganho mensurável: 30,7 s contra 31,1 s e 30,2 s.
Os ~5,5 s restantes não acompanham o intervalo das probes; a causa não foi isolada.

## O que não foi resolvido

1. **O arranque continua em ~31 s.** Os blocos restantes são a preparação do nó com o pull da
   imagem (14 s; 293 MB comprimidos), a criação do container (5 s), o arranque do Python (5 s)
   e a espera final (5,5 s). Três amostras num só dia não descrevem a variação.
2. **O piloto em curso mede com timeout de 30 s.** Uma resposta aos ~31 s seria registrada como
   `timeout`, sem a duração real. O piloto 2 do ADR 0013 usa 60 s por esse motivo.
3. **A cobertura de 14% não foi corrigida.** Depende do agendador do GitHub.
4. **Custo não medido.** Cada arranque mantém a réplica ativa por cerca de cinco minutos, como
   antes; a correção não muda esse tempo.

## Efeito sobre a evidência do piloto 1

A correção altera o sistema medido. Os resultados não devem ser agregados:

- **Slots 0 a 121:** sistema anterior. 17 principais, 0 sucessos.
- **Slot 122 (23:17 a 00:17 UTC):** transição. Inclui duas publicações da API, uma do frontend e
  as três medições acima. Excluir qualquer run deste slot.
- **Slot 123 em diante:** sistema corrigido, mas ainda com timeout de 30 s. A última medição
  manual terminou às 00:12:04 UTC; um run criado até 00:21 UTC pode ter encontrado a réplica
  ainda ativa e também deve ser excluído.

## Artefatos locais

Diretórios ignorados pelo Git, com configuração, tentativas, resumo e marcador de conclusão:

- `data/reports/probe-coldfix-20261114-01-local/`
- `data/reports/probe-coldfix-20261115-02-web/`
- `data/reports/probe-coldfix-20261115-03-web/`

O journal do slot 21 está em `.tools/pilot-artifact-inspection.json`. Os journals dos outros 16
slots não foram lidos nesta análise: baixar artefatos exige autenticação no GitHub. A conclusão
sobre eles apoia-se no nome de cada artefato, que registra `failure` para a principal, e na
repetição do mesmo padrão nos slots 21 e 120 e no ensaio de 2026-11-08.
