-- Clipay.ia — ajustes sobre 0001_init.sql

-- 1. um usuario, uma assinatura (sem duplicatas)
alter table public.subscriptions
  add constraint subscriptions_user_id_key unique (user_id);

-- 2. checagem de username antes do cadastro (o site chama via rpc; anon pode chamar).
-- Devolve so true/false, nao expoe dados de ninguem.
create function public.username_disponivel(nome text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select not exists (select 1 from public.profiles where lower(username) = lower(nome));
$$;

revoke all on function public.username_disponivel(text) from public;
grant execute on function public.username_disponivel(text) to anon, authenticated;

-- 3. so conta ATIVA registra processamento (o app tambem confere, mas o banco e' a barreira final)
drop policy "processamentos_insert_own" on public.processamentos;

create policy "processamentos_insert_own_ativo"
  on public.processamentos for insert
  to authenticated
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.subscriptions s
      where s.user_id = (select auth.uid()) and s.status = 'ativo'
    )
  );
