# Operar o piloto de disponibilidade externa

## Janela aprovada

- Início: **09/11/2026 às 21:17 UTC**, também 21:17 em Lisboa nesta data.
- Fim de novas tentativas: **23/11/2026 às 21:17 UTC**, exclusivo.
- Uma principal por hora; somente após falha, até dois diagnósticos.
- Até 72 inferências por dia completo; retenção dos artefatos: 30 dias.
- Origem: `https://hotelml.vercel.app`; modelo esperado: versão 1.

O workflow só agenda pela branch padrão depois de publicado na `main`. Código apenas local
ou numa PR não ativa o piloto. A configuração está em `monitoring/external-pilot.json`.
Não altere datas, versão ou limites no decorrer do piloto sem registrar uma nova decisão.

## Acompanhar

Abra **Actions → Piloto de sondagem externa**. O cron usa o minuto 17; atrasos podem ocorrer.
O coletor rejeita reexecuções, dispatch manual, runs duplicados do mesmo slot e runs que
chegaram ao próximo slot. Não use re-run para substituir uma falha por um sucesso.

Em cada execução, consulte:

1. `probe-external-20261109-<slot>-success|failure|incomplete`: contém principal e diagnósticos
   em subdiretórios separados. `primary/_SUCCESS` confirma coleta da principal, não saúde.
2. `pilot.json`: resumo que preserva o resultado principal mesmo se os diagnósticos recuperarem.
3. `audit-external-20261109-<run>-<attempt>`: cobertura dos slots e lacunas em `audit.json`.

O job de coleta falha quando a principal falha, mas os artefatos são enviados com `always()`.
Se a instalação, runner ou upload falharem, não conclua que houve indisponibilidade da API.
Depois de noventa minutos, a ausência do artefato é uma lacuna de coleta. Artefatos duplicados
são sinalizados e não entram como sucesso. Arquivos expirados também deixam de ser evidência
disponível: faça a revisão final dentro da retenção.

Para atualizar a auditoria sem gerar tráfego, execute **Run workflow** manualmente na `main`.
Isso ajuda a verificar lacunas se uma execução agendada não ocorreu. Se o Actions parar por
completo, não há detecção independente em tempo real; confira o histórico durante o piloto.

## Investigar falhas

Compare o journal da principal com os diagnósticos e os logs internos da mesma janela.
Uma recuperação diagnóstica não altera a falha principal nem entra na sua taxa de sucesso.
Não subtraia percentis para atribuir tempo ao proxy. O [ensaio inicial](../validation/sondagem-2026-11-08.md)
mostrou 504 externos e 200 internos na janela: ambas as perspectivas são necessárias.

Valide revisão, versão do modelo e motivo operacional antes de qualquer mudança. Escala zero,
timeout de vinte segundos da aplicação e infraestrutura permanecem como estavam. O timeout
de trinta segundos do coletor não altera o timeout do proxy.

## Encerrar ou interromper

O gate bloqueia novas tentativas no fim da janela. A última auditoria precisa aguardar a
tolerância do último slot; a primeira execução horária elegível para desativar o workflow é
**23/11 às 22:17 UTC**. O job de encerramento desativa o agendamento via API GitHub.

Se precisar interromper antes, use **Disable workflow** na página do workflow. Se o último
run não ocorrer ou não tiver permissão para desativar, faça isso manualmente. Mesmo nesse
caso, o gate temporal impede novas tentativas depois do fim; jobs de auditoria ainda podem
rodar até a desativação.

## Revisar os resultados

Revise resultados principais e cobertura separadamente. Slots ausentes são desconhecidos,
não sucesso nem falha de disponibilidade. Compare a primeira tentativa com os diagnósticos,
preserve timeouts e confira custos de réplica, logs, artefatos e runner. O orçamento de
requisições não garante o orçamento financeiro Azure.

Aprovar metas externas ou mudar a política de réplicas exige essa revisão. O piloto não
publica disponibilidade mensal no frontend, não retreina e não prolonga sua própria janela.
Decisões e limites: [ADR 0012](../adr/0012-piloto-coleta-externa.md).
