import Link from "next/link";

const passos = [
  { n: "1", t: "Importe o vídeo bruto", d: "Escolha o arquivo no seu computador. Nada é enviado para a internet." },
  { n: "2", t: "O Clipay.ia corta e dá zoom", d: "Tira silêncio e respiração, aplica o zoom punch-in e transcreve a fala." },
  { n: "3", t: "Você revisa em 1 minuto", d: "Escreve a headline, escolhe o lado do zoom e remove trechos que não quer." },
  { n: "4", t: "Projeto pronto no CapCut", d: "Um projeto novo aparece na sua lista, pronto para exportar." },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-5xl px-6">
      <section className="py-20 text-center">
        <p className="mb-4 text-sm font-medium text-cor2">Para criadores e editores que usam CapCut</p>
        <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
          Do vídeo bruto ao projeto cortado no CapCut, em minutos
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-mudo">
          Corte seco sem respiração, zoom punch-in e headline. A edição chata é feita pelo app, o julgamento
          continua com você.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link href="/cadastro" className="rounded-xl bg-cor px-6 py-3 font-semibold text-white hover:bg-cor2">
            Criar minha conta
          </Link>
          <Link href="/entrar" className="rounded-xl border border-linha px-6 py-3 font-semibold hover:bg-card">
            Já tenho conta
          </Link>
        </div>
      </section>

      <section className="grid gap-4 pb-20 sm:grid-cols-2">
        {passos.map((p) => (
          <div key={p.n} className="rounded-2xl border border-linha bg-card p-6">
            <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-cor/20 text-sm font-bold text-cor2">
              {p.n}
            </div>
            <h2 className="text-lg font-semibold">{p.t}</h2>
            <p className="mt-1 text-mudo">{p.d}</p>
          </div>
        ))}
      </section>

      <section className="mb-20 rounded-2xl border border-linha bg-card p-8">
        <h2 className="text-xl font-semibold">Como funciona a privacidade</h2>
        <p className="mt-2 text-mudo">
          O app roda inteiro no seu Windows: transcrição, cortes e criação do projeto acontecem localmente. Nosso
          servidor só guarda sua conta e quantos projetos você gerou. Nenhum vídeo é enviado.
        </p>
        <p className="mt-3 text-sm text-mudo">Disponível para Windows com CapCut instalado.</p>
      </section>
    </div>
  );
}
