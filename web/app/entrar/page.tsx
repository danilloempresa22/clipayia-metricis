"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Aviso, Campo } from "@/components/Campo";
import { supabase, traduzErro } from "@/lib/supabase";

export default function Entrar() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    setCarregando(true);
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password: senha });
    if (error) {
      setErro(traduzErro(error.message));
      setCarregando(false);
      return;
    }
    router.push("/conta");
  }

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-bold">Entrar</h1>
      <p className="mb-6 mt-1 text-mudo">Use o mesmo e-mail e senha no site e no app.</p>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <form onSubmit={enviar} className="rounded-2xl border border-linha bg-card p-6">
        <Campo id="email" type="email" rotulo="E-mail" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        <Campo id="senha" type="password" rotulo="Senha" value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="current-password" required />
        <button disabled={carregando} className="w-full rounded-xl bg-cor px-5 py-3 font-semibold text-white hover:bg-cor2 disabled:opacity-50">
          {carregando ? "Entrando…" : "Entrar"}
        </button>
      </form>
      <p className="mt-5 text-center text-sm text-mudo">
        Ainda não tem conta? <Link href="/cadastro" className="text-cor2 underline">Criar conta</Link>
      </p>
    </div>
  );
}
