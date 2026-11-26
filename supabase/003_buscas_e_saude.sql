-- =====================================================================
--  Atualização 3: buscas sem resultado (o que as pessoas procuram e
--  não acham no site). O robô manda um resumo por e-mail todo dia.
--  Cole no Supabase → SQL Editor → New query → Run.
-- =====================================================================
create table if not exists public.buscas_vazias (
  termo_norm  text primary key,
  termo       text not null,
  vezes       int not null default 1,
  primeira    timestamptz not null default now(),
  ultima      timestamptz not null default now()
);
create index if not exists buscas_vazias_ultima_idx on public.buscas_vazias (ultima desc);
alter table public.buscas_vazias enable row level security;   -- ninguém lê pelo site
grant all on public.buscas_vazias to service_role;

create or replace function public.registrar_busca_vazia(p_termo text) returns void
language plpgsql security definer set search_path = public as $$
declare t text := left(trim(coalesce(p_termo, '')), 120);
        n text := public.normaliza(t);
begin
  if length(n) < 3 then return; end if;
  insert into buscas_vazias (termo_norm, termo) values (n, t)
  on conflict (termo_norm) do update set vezes = buscas_vazias.vezes + 1, termo = excluded.termo, ultima = now();
end $$;
revoke all on function public.registrar_busca_vazia(text) from public;
grant execute on function public.registrar_busca_vazia(text) to anon, authenticated;
