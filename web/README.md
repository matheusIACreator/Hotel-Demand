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
