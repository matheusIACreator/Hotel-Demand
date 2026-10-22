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
