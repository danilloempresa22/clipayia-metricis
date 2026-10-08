-- Clipay.ia — nome da pessoa no perfil (a tela Conta do app edita).
-- Rode no SQL Editor do Supabase (projeto oslrmcxzbsneherutmyn). Pode rodar mais de uma vez.

-- 1. a coluna
alter table public.profiles add column if not exists nome text;

-- 2. a pessoa pode atualizar SO a propria linha...
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- 3. ...e SO a coluna nome (username e o resto continuam travados)
revoke update on public.profiles from authenticated;
grant update (nome) on public.profiles to authenticated;

-- 4. um limite simples de tamanho
alter table public.profiles drop constraint if exists profiles_nome_tamanho;
alter table public.profiles add constraint profiles_nome_tamanho check (nome is null or char_length(nome) <= 80);
