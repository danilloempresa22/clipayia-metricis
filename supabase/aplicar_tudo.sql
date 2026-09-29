-- Clipay.ia — schema inicial (Supabase / Postgres)
-- Convenção: RLS ligado em todas as tabelas; auth.uid() sempre entre parênteses
-- "(select auth.uid())" para o Postgres avaliar uma vez só por query, não por linha.

-- 1. profiles: dados públicos do usuário, 1:1 com auth.users
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  username text not null,
  created_at timestamptz not null default now()
);

create unique index profiles_username_lower_idx on public.profiles (lower(username));

alter table public.profiles enable row level security;

create policy "profiles_select_own"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = id);

create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- 2. subscriptions: status da conta (ativo/inativo). MVP sem cobrança automática —
-- só Danillo ativa/desativa (via service role no SQL editor do Supabase ou painel admin futuro).
create table public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  status text not null default 'inativo' check (status in ('ativo', 'inativo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index subscriptions_user_id_idx on public.subscriptions (user_id);

alter table public.subscriptions enable row level security;

-- usuário só LÊ o próprio status; nenhuma policy de insert/update para "authenticated"
create policy "subscriptions_select_own"
  on public.subscriptions for select
  to authenticated
  using ((select auth.uid()) = user_id);

-- 3. processamentos: contador de uso, nenhum vídeo é enviado ou armazenado
create table public.processamentos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);

create index processamentos_user_id_idx on public.processamentos (user_id);

alter table public.processamentos enable row level security;

create policy "processamentos_select_own"
  on public.processamentos for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "processamentos_insert_own"
  on public.processamentos for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

-- 4. ao criar usuário (cadastro no site), cria profile + subscription (inativo) automaticamente
create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, username)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'username', split_part(new.email, '@', 1)));

  insert into public.subscriptions (user_id, status)
  values (new.id, 'inativo');

  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 5. updated_at automático em subscriptions
create function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger subscriptions_set_updated_at
  before update on public.subscriptions
  for each row execute function public.set_updated_at();

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
