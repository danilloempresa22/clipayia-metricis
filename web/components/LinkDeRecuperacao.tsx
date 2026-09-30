"use client";

import { useEffect } from "react";

// Rede de seguranca: se o link "Esqueceu a senha?" do e-mail cair em qualquer pagina do site
// (ex.: a inicial), leva pro formulario de senha nova mantendo o token que vem depois do #.
export function LinkDeRecuperacao() {
  useEffect(() => {
    const h = window.location.hash;
    if (h.includes("type=recovery") && window.location.pathname !== "/redefinir-senha") {
      window.location.replace("/redefinir-senha" + h);
    }
  }, []);
  return null;
}
