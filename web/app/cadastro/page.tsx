"use client";

import Link from "next/link";
import { useState } from "react";
import { Aviso, Campo } from "@/components/Campo";
import { supabase, traduzErro } from "@/lib/supabase";

const USERNAME_OK = /^[a-zA-Z0-9_.]{3,20}$/;

export default function Cadastro() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [carregando, setCarregando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    if (!USERNAME_OK.test(username)) return setErro("O nome de usuário deve ter de 3 a 20 caracteres: letras, números, ponto ou _.");
    if (senha.length < 8) return setErro("Use uma senha com pelo menos 8 caracteres.");
    setCarregando(true);
    try {
      const livre = await supabase.rpc("username_disponivel", { nome: username });
      if (livre.error) throw livre.error;
      if (!livre.data) return setErro("Esse nome de usuário já está em uso. Escolha outro.");

      const { error } = await supabase.auth.signUp({
        email: email.trim(),
        password: senha,
        options: { data: { username }, emailRedirectTo: `${window.location.origin}/conta` },
      });
      if (error) throw error;
      setEnviado(true);
    } catch (err) {
      setErro(traduzErro(err instanceof Error ? err.message : String(err)));
    } finally {
      setCarregando(false);
    }
  }

  if (enviado)
    return (
      <div className="mx-auto max-w-md px-6 py-16">
        <h1 className="text-2xl font-bold">Confira seu e-mail</h1>
        <p className="mt-3 text-mudo">
          Enviamos um link de confirmação para <b className="text-txt">{email}</b>. Depois de confirmar, é só{" "}
          <Link href="/entrar" className="text-cor2 underline">entrar</Link>.
        </p>
        <p className="mt-3 text-sm text-mudo">
          Sua conta começa <b>inativa</b>: a liberação do acesso é feita manualmente. Não achou o e-mail? Olhe o spam.
        </p>
      </div>
    );

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-bold">Criar conta</h1>
      <p className="mb-6 mt-1 text-mudo">Leva menos de um minuto.</p>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <form onSubmit={enviar} className="rounded-2xl border border-linha bg-card p-6">
        <Campo id="username" rotulo="Nome de usuário" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        <Campo id="email" type="email" rotulo="E-mail" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
        <Campo id="senha" type="password" rotulo="Senha" dica="Pelo menos 8 caracteres." value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="new-password" required />
        <button disabled={carregando} className="w-full rounded-xl bg-cor px-5 py-3 font-semibold text-white hover:bg-cor2 disabled:opacity-50">
          {carregando ? "Criando…" : "Criar conta"}
        </button>
      </form>
      <p className="mt-5 text-center text-sm text-mudo">
        Já tem conta? <Link href="/entrar" className="text-cor2 underline">Entrar</Link>
      </p>
    </div>
  );
}
