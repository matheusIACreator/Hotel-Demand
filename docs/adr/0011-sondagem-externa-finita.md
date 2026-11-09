# ADR 0011: Sondagem externa finita com inferência sintética

- **Status:** aceito
- **Data:** 2026-11-08

## Contexto

Os SLIs internos não observam falhas anteriores ao processo, espera por réplica ou o caminho
da Vercel. Uma exportação sem eventos também não permite distinguir ausência de tráfego de
perda na coleta. É necessário medir do lado do cliente sem criar um monitor recorrente que
mantenha a réplica acordada ou gere custos sem orçamento definido.

## Decisão

`hotelml probe` executa uma amostra finita de inferências com uma reserva sintética fixa,
validada pelo contrato `Booking`. `--target azure` chama `/predict`; `--target web` chama
`/api/predict` com o contrato do proxy Next.js. A origem deve usar HTTPS, sem credenciais,
caminho, query ou fragmento; HTTP fica disponível somente para loopback em desenvolvimento.

Não há chamada de readiness, aquecimento, retry ou acompanhamento de redirects. Cada tentativa
equivale a um POST. O padrão é três tentativas, com cinco segundos após a conclusão da anterior;
o limite é vinte. Intervalo e timeout de socket não podem superar sessenta segundos. DNS e
leituras sucessivas não têm um prazo total garantido por esse timeout da biblioteca padrão.

A duração vai do início da chamada HTTP até a leitura e validação da resposta. Inclui o caminho
do cliente, estabelecimento de conexão, rede, ingress e inferência; no alvo web, inclui também
o proxy da Vercel. Não mede renderização, JavaScript no navegador ou o clique do usuário.
A medição não identifica automaticamente cold start: a primeira tentativa pode encontrar
réplica ativa, e chamadas subsequentes podem manter a réplica acordada.

Somente uma resposta 2xx com previsão válida conta como sucesso. O avaliador verifica uma
previsão no alvo Azure, probabilidade finita em [0, 1], decisão consistente com o limiar 0,5,
nome e versão preenchidos; no alvo web, exige também `ok=true` e `threshold=0.5`. Uma versão
esperada opcional permite detectar a publicação de outro modelo. Essa verificação é semântica
mínima, não uma duplicação completa do schema de resposta da aplicação.

Todas as falhas entram no denominador, inclusive 4xx/429, redirects, erros de rede, timeout,
resposta inválida ou maior que 64 KiB. Isso difere da exclusão de 4xx dos SLIs internos: aqui
a ferramenta controla a reserva válida enviada e mede se a inferência sintética foi atendida.
P50/P95/P99 consideram somente sucessos; uma taxa de sucesso baixa não pode ser ocultada pelo
percentil de poucas respostas rápidas. Não há percentis de sucesso quando todos os pedidos falham.

## Artefatos e consequências

A saída é um diretório novo. `run.json` registra a configuração e hash do payload sintético;
`attempts.jsonl` persiste cada tentativa concluída com flush; `summary.json` agrega resultados
e hashes; `_SUCCESS` confirma conclusão da coleta. Esse marcador não indica que a API esteve
saudável. Interrupção ou falha inesperada deixam artefatos parciais, sem marcador.

Não persistimos reserva, probabilidades, corpo de resposta, cabeçalhos ou mensagens de exceção.
Os artefatos contêm apenas origem pública, metadados do modelo e resultados operacionais.
Código 2 indica pelo menos uma tentativa falhada; código 0 indica todas bem-sucedidas.
Uma falha não é repetida para substituí-la por sucesso.

A taxa observada descreve apenas a amostra, este cliente e este período. `slo_status=not_evaluated`
evita transformar poucas sondagens em compromisso ou medição de disponibilidade mensal.
Os artefatos externos não devem ser convertidos em eventos internos de `hotelml slo`.
Agendamento, objetivos externos, localização do coletor e tratamento de falhas do próprio
monitor dependem de política operacional e orçamento específicos e continuam fora deste ensaio.
