"use client";

import { useEffect, useState } from "react";
import { Aviso, Campo } from "@/components/Campo";
import { supabase, traduzErro } from "@/lib/supabase";

// Destino do link "Esqueceu a senha?" (enviado pelo app ou pelo site). O supabase-js lê o token do link sozinho.
export default function RedefinirSenha() {
  const [estado, setEstado] = useState<"verificando" | "pronto" | "invalido" | "feito">("verificando");
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((evento, sessao) => {
      if (evento === "PASSWORD_RECOVERY" || sessao) setEstado("pronto");
    });
    const erroNoLink = new URLSearchParams(window.location.hash.slice(1)).get("error_description");
    const t = setTimeout(async () => {
      const { data: s } = await supabase.auth.getSession();
      setEstado((e) => (e !== "verificando" ? e : s.session && !erroNoLink ? "pronto" : "invalido"));
    }, 1500);
    return () => { data.subscription.unsubscribe(); clearTimeout(t); };
  }, []);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setErro("");
    if (senha.length < 8) return setErro("Use uma senha com pelo menos 8 caracteres.");
    if (senha !== confirma) return setErro("As duas senhas não são iguais.");
    setSalvando(true);
    const { error } = await supabase.auth.updateUser({ password: senha });
    setSalvando(false);
    if (error) return setErro(traduzErro(error.message));
    await supabase.auth.signOut();
    setEstado("feito");
  }

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-bold">Definir senha nova</h1>
      {estado === "verificando" && <p className="mt-3 text-mudo">Conferindo o link…</p>}
      {estado === "invalido" && (
        <div className="mt-6">
          <Aviso tipo="erro">Esse link é inválido ou já expirou. Peça um novo em “Esqueceu a senha?” no Clipay.ia.</Aviso>
        </div>
      )}
      {estado === "feito" && (
        <div className="mt-6">
          <Aviso tipo="ok">Senha alterada. Volte ao Clipay.ia e entre com a senha nova.</Aviso>
        </div>
      )}
      {estado === "pronto" && (
        <>
          <p className="mb-6 mt-1 text-mudo">Escolha a senha que você vai usar no app e no site.</p>
          {erro && <Aviso tipo="erro">{erro}</Aviso>}
          <form onSubmit={salvar} className="rounded-2xl border border-linha bg-card p-6">
            <Campo id="senha" type="password" rotulo="Senha nova" dica="Pelo menos 8 caracteres." value={senha}
              onChange={(e) => setSenha(e.target.value)} autoComplete="new-password" required />
            <Campo id="confirma" type="password" rotulo="Repita a senha" value={confirma}
              onChange={(e) => setConfirma(e.target.value)} autoComplete="new-password" required />
            <button disabled={salvando} className="w-full rounded-xl bg-cor px-5 py-3 font-semibold text-white hover:bg-cor2 disabled:opacity-50">
              {salvando ? "Salvando…" : "Salvar senha nova"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
