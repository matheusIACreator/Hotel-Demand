// O template é recriado a cada navegação, o que dispara a entrada suave da página.
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="animate-page-in">{children}</div>
}
