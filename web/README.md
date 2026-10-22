# hotelml · frontend

Interface web do hotelml em Next.js, TypeScript, Tailwind e shadcn/ui. O projeto foi criado com
`npx shadcn@latest init` (template Next.js, preset Nova, Radix).

```bash
cd web
npm install
npm run dev            # http://localhost:3000
npm run lint           # ESLint
npm run format:check   # Prettier (o CI verifica)
npm run typecheck      # tsc --noEmit
npm test               # Vitest
npm run build
```

O CI usa `npm ci`, que exige o `package-lock.json` em sincronia. Atualize o lock com npm 11.21 ou
mais recente (por exemplo `npx npm@11 install`): o npm 11.6 omitia dependências opcionais de
outras plataformas, como `@emnapi/*`, e o `npm ci` no Linux falhava.

## Identidade visual

Os tokens ficam em `app/globals.css`: bege `#F7F4EE` como fundo, branco neve `#FFFDFA` nas
superfícies de leitura e castanho `#655541` na ação principal. Verde oliva, âmbar e terracota
são reservados para estados e resultados. O texto secundário usa `#6C645A`, um pouco mais escuro
que `#71695F`, para atingir contraste AA também sobre a areia `#EDE4D6`.
`lib/contrast.test.ts` lê a paleta do CSS e falha se algum par de texto ficar abaixo de 4,5:1.

Geist é usada em textos e números; Newsreader, serifada, apenas nos títulos. As animações de
entrada duram cerca de 200 ms e são desativadas com `prefers-reduced-motion`.

## Integração com a API

O navegador nunca chama a Azure diretamente: `app/api/health` e `app/api/predict` são rotas de
servidor que leem `HOTELML_API_URL`, aplicam timeout (8 s na saúde, 20 s na previsão) e
convertem as respostas em estados explícitos (`lib/server/hotelml-api.ts`). Copie
`.env.example` para `.env.local` para desenvolvimento; na Vercel, defina a variável no projeto.

A Container App escala para zero réplicas. Timeouts e respostas 502/503/504 são tratados como
"Iniciando o serviço…": o navegador volta a consultar `/api/health` com intervalos crescentes
durante até 3 minutos e para assim que a API fica pronta, para não manter a réplica acordada.

## Contrato

- `lib/contract/openapi.json` é exportado da FastAPI com `python scripts/export_openapi.py`.
  `tests/test_openapi_contract.py` falha no CI do Python se o ficheiro ficar desatualizado.
- `lib/contract/booking.ts` é o espelho em Zod do `Booking`. `booking.test.ts` compara campos,
  obrigatoriedade, nulidade e limites com o OpenAPI; o Zod só pode ser mais estrito.
- `lib/contract/categories.json` lista as categorias aprendidas pelo `OneHotEncoder` do bundle
  (versão e run identificados no ficheiro), gerado por `python scripts/export_categories.py`.
  Categorias raras são agrupadas pelo modelo como "infrequentes".
- `lib/contract/example-booking.json` é uma reserva sintética de `make_synthetic`, não um registo
  do dataset real.
- O limiar de decisão (0,5) está fixo em `src/hotelml/api.py` e não vem na resposta da API;
  `DECISION_THRESHOLD` replica esse valor.

## Testes end-to-end e acessibilidade

```bash
npm run build
npm run test:e2e       # Playwright em desktop e celular, contra o build de produção
```

As rotas `/api/*` são simuladas no navegador, então os testes não chamam a Azure. Cada página é
verificada com axe (WCAG 2.1 A/AA) com `prefers-reduced-motion`, para avaliar as cores finais e
não um quadro da animação. Os testes cobrem também o fluxo do simulador, a inicialização a frio,
o envio pelo teclado, o link "Pular para o conteúdo", o menu do celular e a página 404.

## Deploy na Vercel

1. Importe o repositório na Vercel e defina **Root Directory** como `web` (framework Next.js).
2. Em *Environment Variables*, crie `HOTELML_API_URL` com a URL da API, sem barra final, para
   Production e Preview. A variável só é lida no servidor; nunca use o prefixo `NEXT_PUBLIC_`.
3. Os previews de cada pull request chamam a mesma API pública de demonstração.

A primeira previsão depois de uma pausa pode esperar a Container App sair de zero réplicas; a
interface mostra "Iniciando o serviço…" e repete a previsão quando a API fica pronta.

## Dados exibidos

Nenhum número é escrito à mão. As métricas da página Modelo vêm de
`python scripts/export_model_card.py`, que lê o run MLflow da versão registada e falha se o
dataset local não reproduzir a divisão do treino. Ao promover outra versão, exporte de novo o
cartão, as categorias e o contrato; `lib/model-card.test.ts` exige que cartão e categorias
descrevam a mesma versão. A página também permite conferir a versão carregada na API.
