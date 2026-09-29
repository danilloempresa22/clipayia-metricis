import { createClient } from "@supabase/supabase-js";

// Chave publicável: pública por desenho. Quem protege os dados é o RLS do banco.
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
);

// Link permanente: sempre aponta para a release mais recente do GitHub.
export const DOWNLOAD_URL =
  process.env.NEXT_PUBLIC_DOWNLOAD_URL ||
  "https://github.com/danilloempresa22/clipayia-metricis/releases/latest/download/Clipay.exe";

// Traduz os erros mais comuns do Supabase Auth para português.
export function traduzErro(msg: string): string {
  const m = msg.toLowerCase();
  if (m.includes("invalid login")) return "E-mail ou senha incorretos.";
  if (m.includes("not confirmed")) return "Confirme seu e-mail (link enviado no cadastro) antes de entrar.";
  if (m.includes("already registered") || m.includes("already been registered")) return "Esse e-mail já tem cadastro. Tente entrar.";
  if (m.includes("rate limit") || m.includes("too many")) return "Muitas tentativas. Aguarde alguns minutos e tente de novo.";
  if (m.includes("password") && m.includes("6")) return "A senha precisa ter pelo menos 6 caracteres.";
  if (m.includes("fetch") || m.includes("network")) return "Sem conexão com a internet.";
  return "Algo deu errado. Tente de novo.";
}
