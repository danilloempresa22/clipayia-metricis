import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";
import { LinkDeRecuperacao } from "@/components/LinkDeRecuperacao";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Clipay.ia — cortes e zoom no CapCut, sem trabalho manual",
  description:
    "Importe o vídeo bruto e receba um projeto novo no CapCut já cortado, com zoom e headline. Tudo roda no seu computador.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className={`${geistSans.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">
        <header className="border-b border-linha">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-xl font-bold tracking-tight">
              Clipay<span className="text-cor2">.ia</span>
            </Link>
            <nav className="flex items-center gap-5 text-sm">
              <Link href="/entrar" className="text-mudo hover:text-txt">
                Entrar
              </Link>
              <Link href="/cadastro" className="rounded-lg bg-cor px-4 py-2 font-semibold text-white hover:bg-cor2">
                Criar conta
              </Link>
            </nav>
          </div>
        </header>
        <LinkDeRecuperacao />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-linha py-6 text-center text-xs text-mudo">
          © {new Date().getFullYear()} Clipay.ia · Seus vídeos nunca saem do seu computador.
        </footer>
      </body>
    </html>
  );
}
