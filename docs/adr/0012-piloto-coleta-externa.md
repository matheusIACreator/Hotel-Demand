# ADR 0012: Piloto de coleta externa por quatorze dias

- **Status:** aceito; política aprovada pelo responsável em 2026-11-09
- **Data:** 2026-11-09

## Política

Manter escala a zero e os timeouts da aplicação. Coletar uma tentativa principal por hora
pelo caminho Vercel → Azure, sem readiness anterior. Se a principal falhar, executar até duas
tentativas de diagnóstico, com cinco segundos de intervalo. Diagnóstico não muda o resultado
principal. A reserva é sintética e a versão esperada é 1.

O piloto começa em **2026-11-09 às 21:17 UTC** e termina em **2026-11-23 às 21:17 UTC**, com fim
exclusivo: são 336 slots horários. A configuração versionada está em
`monitoring/external-pilot.json`. O limite planejado é 24 tentativas principais e até 48
diagnósticos por dia completo, até 1.008 chamadas em todo o piloto. Limite de requisições não
é teto monetário: tempo de réplica, logs, armazenamento e runner também precisam ser revistos.
Não se altera o orçamento Azure nem se usa sondagem frequente para manter a réplica acordada.

## Execução e encerramento

O workflow `external-probe.yml` usa cron no minuto 17, concorrência serial e jobs com limite de
tempo. Um gate anterior à instalação das dependências bloqueia tráfego fora da janela, em
dispatch manual e em reexecuções. Antes de medir, o coletor consulta o histórico do próprio
workflow e permite somente o primeiro run agendado criado para o slot. Runs atrasados até outro
slot são descartados; não há compensação de slots perdidos com uma rajada de chamadas.

A ausência de acesso à API GitHub ou paginação incompleta impede a coleta antes do tráfego.
A reserva usa o histórico de criação de runs, não um horário planejado fornecido pelo GitHub;
atrasos continuam possíveis e os timestamps efetivos ficam nos artefatos. A primeira coleta
de cada slot é o sinal principal; as demais têm finalidade diagnóstica.

Cada nova tentativa verifica o slot e a janela antes de iniciar. Chamadas já iniciadas podem
terminar depois do corte, e o timeout de socket não garante prazo total de DNS/HTTP. O limite
de dez minutos do job protege o runner de espera indefinida. Interrupções preservam artefatos
parciais sempre que o runner consegue executar o upload final.

Depois do fim, nenhum novo slot é elegível. Há uma última auditoria após a tolerância de coleta
do último slot; o job de encerramento desativa o workflow com `actions:write`. Os jobs de coleta
e auditoria têm somente `contents:read` e `actions:read`. Se o encerramento falhar ou não for
agendado, o gate temporal continua bloqueando tráfego; deve-se desativar o workflow manualmente.

## Evidência e lacunas

Artefatos ficam por trinta dias. A principal e cada diagnóstico conservam seu próprio journal,
configuração e resumo. O nome do artefato registra piloto, slot e resultado principal publicado
somente depois de concluir a principal. O nome é um índice operacional de artefatos produzidos
por este workflow confiável; não substitui os journals para investigação ou é prova assinada.

A auditoria compara os 336 slots com os artefatos não expirados. Distingue sucesso, falha da
principal, coleta incompleta, duplicação, pendência e ausência. Uma ausência só vira lacuna
depois de noventa minutos do horário planejado. Taxa de sucesso usa somente principais com
resultado; cobertura informa separadamente quantos slots têm resultado. Não se preenche lacuna
como sucesso nem como indisponibilidade da API.

Um dispatch manual executa apenas auditoria, sem inferência. A auditoria depende do mesmo
GitHub Actions: se todo o agendador parar, a lacuna só ficará visível numa execução posterior
ou inspeção manual. Este piloto não fornece um heartbeat independente nem alerta de ausência
em tempo real. Não promete SLO de produção.

## Revisão após o piloto

Revisar primeiras tentativas, falhas, durações, cobertura, diagnósticos e custos observados.
Não excluir chamadas iniciais nem substituir suas falhas por recuperações posteriores.
Definir metas e avaliar a política de réplicas com essa evidência. Não prolongar a janela nem
reativar coleta automaticamente: um novo piloto requer uma nova decisão explícita.
