"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Aviso } from "@/components/Campo";
import { DOWNLOAD_URL, supabase } from "@/lib/supabase";

type Dados = { username: string; email: string; status: "ativo" | "inativo"; usos: number };

export default function Conta() {
  const router = useRouter();
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    (async () => {
      const { data } = await supabase.auth.getSession();
      const user = data.session?.user;
      if (!user) return router.replace("/entrar");
      const [perfil, ass, usos] = await Promise.all([
        supabase.from("profiles").select("username").eq("id", user.id).maybeSingle(),
        supabase.from("subscriptions").select("status").eq("user_id", user.id).maybeSingle(),
        supabase.from("processamentos").select("id", { count: "exact", head: true }).eq("user_id", user.id),
      ]);
      if (perfil.error || ass.error) return setErro("Não consegui carregar sua conta. Atualize a página.");
      setDados({
        username: perfil.data?.username ?? user.email ?? "",
        email: user.email ?? "",
        status: ass.data?.status === "ativo" ? "ativo" : "inativo",
        usos: usos.count ?? 0,
      });
    })();
  }, [router]);

  async function sair() {
    await supabase.auth.signOut();
    router.push("/");
  }

  if (erro) return <div className="mx-auto max-w-2xl px-6 py-16"><Aviso tipo="erro">{erro}</Aviso></div>;
  if (!dados) return <div className="mx-auto max-w-2xl px-6 py-16 text-mudo">Carregando…</div>;

  const ativo = dados.status === "ativo";
  return (
    <div className="mx-auto max-w-2xl px-6 py-14">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Olá, {dados.username}</h1>
          <p className="text-sm text-mudo">{dados.email}</p>
        </div>
        <button onClick={sair} className="text-sm text-mudo hover:text-txt">Sair</button>
      </div>

      <section className="mb-5 rounded-2xl border border-linha bg-card p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-mudo">Status da conta</p>
            <p className={`text-xl font-semibold ${ativo ? "text-ok" : "text-aviso"}`}>{ativo ? "Ativa" : "Aguardando ativação"}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-mudo">Projetos gerados</p>
            <p className="text-xl font-semibold">{dados.usos}</p>
          </div>
        </div>
        {!ativo && (
          <p className="mt-4 text-sm text-mudo">
            O acesso é liberado manualmente. Assim que sua conta for ativada, o app passa a funcionar — não precisa
            baixar nada de novo.
          </p>
        )}
      </section>

      <section className="mb-5 rounded-2xl border border-linha bg-card p-6">
        <h2 className="text-lg font-semibold">Baixar o app (Windows)</h2>
        <p className="mt-1 text-sm text-mudo">Um único arquivo. Não precisa instalar nada.</p>
        {DOWNLOAD_URL ? (
          <a href={DOWNLOAD_URL} className="mt-4 inline-block rounded-xl bg-cor px-5 py-3 font-semibold text-white hover:bg-cor2">
            Baixar o Clipay.ia
          </a>
        ) : (
          <p className="mt-4 inline-block rounded-xl border border-linha px-5 py-3 text-mudo">Download disponível em breve</p>
        )}
      </section>

      <section className="rounded-2xl border border-linha bg-card p-6">
        <h2 className="text-lg font-semibold">Ao abrir pela primeira vez</h2>
        <p className="mt-1 text-sm text-mudo">
          O Windows vai mostrar “O Windows protegeu o seu computador”. É esperado: o app ainda não tem assinatura digital.
        </p>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-mudo">
          <li>Clique em <b className="text-txt">Mais informações</b>.</li>
          <li>Clique em <b className="text-txt">Executar assim mesmo</b>.</li>
          <li>O app abre no seu navegador. Entre com o mesmo e-mail e senha daqui.</li>
        </ol>
        <p className="mt-3 text-sm text-mudo">Na primeira análise o app baixa o modelo de transcrição (precisa de internet uma vez).</p>
      </section>
    </div>
  );
}
