import type { InputHTMLAttributes } from "react";

export function Campo({ rotulo, dica, ...props }: { rotulo: string; dica?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="mb-4">
      <label htmlFor={props.id} className="mb-1.5 block text-sm text-mudo">
        {rotulo}
      </label>
      <input
        {...props}
        className="w-full rounded-xl border border-linha bg-bg px-4 py-3 text-txt placeholder:text-mudo/60"
      />
      {dica && <p className="mt-1 text-xs text-mudo">{dica}</p>}
    </div>
  );
}

export function Aviso({ tipo, children }: { tipo: "erro" | "ok" | "aviso"; children: React.ReactNode }) {
  const cores = {
    erro: "border-erro/40 bg-erro/10 text-erro",
    ok: "border-ok/40 bg-ok/10 text-ok",
    aviso: "border-aviso/40 bg-aviso/10 text-aviso",
  }[tipo];
  return (
    <div role={tipo === "erro" ? "alert" : "status"} className={`mb-4 rounded-xl border px-4 py-3 text-sm ${cores}`}>
      {children}
    </div>
  );
}
