-- =====================================================================
--  Atualização 2: filtros do catálogo (cor, tom de pele) e vitrine
--  Cole no Supabase → SQL Editor → New query → Run.
-- =====================================================================
alter table public.catalogo add column if not exists familia text;
alter table public.catalogo add column if not exists tom text;
create index if not exists catalogo_grupo_idx on public.catalogo (grupo);

create table if not exists public.vitrine (
  grupo             text primary key,
  marca             text,
  nome              text not null,
  categoria         text,
  imagem            text,
  preco_min         numeric(10,2),
  loja_min          text,
  url_min           text,
  lojas             text[] not null default '{}',
  lojas_disponiveis text[] not null default '{}',
  n_lojas           int not null default 0,
  n_cores           int not null default 0,
  disponivel        boolean not null default false,
  familias          text[] not null default '{}',
  tons              text[] not null default '{}',
  busca             text,
  atualizado_em     timestamptz not null default now()
);
create index if not exists vitrine_cat_idx on public.vitrine (categoria);
create index if not exists vitrine_preco_idx on public.vitrine (preco_min);
create index if not exists vitrine_lojas_idx on public.vitrine using gin (lojas);
create index if not exists vitrine_familias_idx on public.vitrine using gin (familias);
create index if not exists vitrine_tons_idx on public.vitrine using gin (tons);
create index if not exists vitrine_busca_trgm on public.vitrine using gin (busca gin_trgm_ops);

alter table public.vitrine enable row level security;
drop policy if exists "vitrine publica" on public.vitrine;
create policy "vitrine publica" on public.vitrine for select to anon, authenticated using (true);
grant select on public.vitrine to anon, authenticated;
grant all on public.vitrine to service_role;

-- lista de marcas para o filtro (com contagem)
create or replace function public.marcas_vitrine() returns table(marca text, total bigint)
language sql stable security definer set search_path = public as $$
  select marca, count(*) from vitrine where marca is not null group by marca order by count(*) desc, marca
$$;
grant execute on function public.marcas_vitrine() to anon, authenticated;
