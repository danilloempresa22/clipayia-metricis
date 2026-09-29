# Operação do Clipay.ia

## Ativar / desativar uma conta (manual, no MVP)
Supabase → **SQL Editor** → rode (troque o e-mail):

```sql
-- ativar
update public.subscriptions set status = 'ativo'
where user_id = (select id from auth.users where email = 'cliente@exemplo.com');

-- desativar
update public.subscriptions set status = 'inativo'
where user_id = (select id from auth.users where email = 'cliente@exemplo.com');
```

O app confere o status a cada análise, então a mudança vale na hora (sem baixar nada de novo).

## Ver quem está cadastrado e quanto usou
```sql
select p.username, u.email, s.status, count(pr.id) as projetos, u.created_at
from auth.users u
join public.profiles p on p.id = u.id
join public.subscriptions s on s.user_id = u.id
left join public.processamentos pr on pr.user_id = u.id
group by p.username, u.email, s.status, u.created_at
order by u.created_at desc;
```

## Criar um usuário de teste sem e-mail de confirmação
Supabase → Authentication → Users → **Add user** (marque *Auto Confirm User*), depois ative com o SQL acima.

## Confirmação de e-mail
Hoje o Supabase exige confirmar o e-mail (o e-mail grátis tem limite de envios por hora).
Para desligar: Authentication → Providers → Email → *Confirm email*.

## Chaves
- `anon` / publishable: públicas, ficam no app e no site.
- `service_role`: **nunca** no código, no app ou no site. Só o SQL Editor a usa (por baixo dos panos).

## Rodar em desenvolvimento
- App: `app\.venv\Scripts\python.exe app\app.py --navegador`
- Site: `cd web` → `npm run dev` (http://localhost:3000)
- Testes: `app\.venv\Scripts\python.exe -m pytest tests`
