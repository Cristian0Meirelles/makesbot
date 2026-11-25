-- =====================================================================
--  Voltou! — banco de dados (Supabase / Postgres)
--  Cole TUDO isto no Supabase → SQL Editor → New query → Run.
--  Pode rodar de novo sem medo: o script é idempotente.
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- Produtos que alguém quer (público: sem dados pessoais)
-- ---------------------------------------------------------------------
create table if not exists public.produtos (
  id                 uuid primary key default gen_random_uuid(),
  categoria          text not null,
  marca              text not null,
  nome               text not null,
  cor                text,
  foto_url           text,                -- foto enviada pela pessoa
  links              text[] not null default '{}', -- links diretos (opcional)
  chave              text not null unique,         -- marca|nome|cor normalizado
  imagem_loja        text,                -- melhor imagem encontrada nas lojas
  disponivel         boolean not null default false,
  disponivel_desde   timestamptz,
  ultima_verificacao timestamptz,
  ativo              boolean not null default true,
  criado_em          timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Ofertas encontradas pelo bot (público: vitrine do site)
-- ---------------------------------------------------------------------
create table if not exists public.ofertas (
  id            uuid primary key default gen_random_uuid(),
  produto_id    uuid not null references public.produtos(id) on delete cascade,
  loja          text not null,
  titulo        text not null,
  url           text not null,
  url_afiliado  text,
  imagem        text,
  preco         numeric(10,2),
  disponivel    boolean not null default false,
  atualizado_em timestamptz not null default now()
);
create index if not exists ofertas_produto_idx on public.ofertas(produto_id);

-- ---------------------------------------------------------------------
-- Lojas monitoradas (o bot atualiza; o site mostra)
-- ---------------------------------------------------------------------
create table if not exists public.lojas (
  nome        text primary key,
  dominio     text,
  tipo        text,
  frequencia  text,
  ok          boolean,
  atualizado_em timestamptz default now()
);

-- ---------------------------------------------------------------------
-- Catálogo (o bot varre as lojas a cada 6h; o site usa no autocompletar)
-- ---------------------------------------------------------------------
create extension if not exists pg_trgm;

create table if not exists public.catalogo (
  id            bigserial primary key,
  loja          text not null,
  marca         text,
  produto       text not null,    -- nome do produto (ex.: Powder Blush)
  cor           text,             -- variação/cor (ex.: Film Noir)
  categoria     text,             -- Blush, Batom, Gloss...
  titulo        text not null,
  url           text not null,
  url_afiliado  text,
  imagem        text,
  preco         numeric(10,2),
  disponivel    boolean not null default false,
  busca         text not null,    -- texto normalizado (marca produto cor categoria)
  grupo         text not null,    -- marca|produto normalizado (junta as cores)
  atualizado_em timestamptz not null default now(),
  unique (loja, url)
);
create index if not exists catalogo_busca_trgm on public.catalogo using gin (busca gin_trgm_ops);
create index if not exists catalogo_grupo_idx on public.catalogo (grupo);
alter table public.catalogo enable row level security;
drop policy if exists "catalogo publico" on public.catalogo;
create policy "catalogo publico" on public.catalogo for select to anon, authenticated using (true);

-- ---------------------------------------------------------------------
-- Inscrições (PRIVADO: e-mail / WhatsApp de quem quer ser avisado)
-- ---------------------------------------------------------------------
create table if not exists public.inscricoes (
  id            uuid primary key default gen_random_uuid(),
  produto_id    uuid not null references public.produtos(id) on delete cascade,
  nome          text,
  email         text,
  whatsapp      text,
  callmebot_key text,
  token         uuid not null default gen_random_uuid() unique, -- para cancelar
  ativo         boolean not null default true,
  criado_em     timestamptz not null default now()
);
create index if not exists inscricoes_produto_idx on public.inscricoes(produto_id) where ativo;

-- ---------------------------------------------------------------------
-- Histórico de avisos enviados (PRIVADO)
-- ---------------------------------------------------------------------
create table if not exists public.avisos (
  id           bigserial primary key,
  inscricao_id uuid references public.inscricoes(id) on delete cascade,
  produto_id   uuid references public.produtos(id) on delete cascade,
  loja         text,
  canal        text,
  ok           boolean,
  erro         text,
  enviado_em   timestamptz not null default now()
);
create index if not exists avisos_busca_idx on public.avisos(inscricao_id, loja, enviado_em desc);

-- ---------------------------------------------------------------------
-- Segurança (RLS): o site só LÊ produtos/ofertas/lojas.
-- Inscrições e avisos ficam invisíveis para o público.
-- O bot usa a chave service_role, que ignora RLS.
-- ---------------------------------------------------------------------
alter table public.produtos   enable row level security;
alter table public.ofertas    enable row level security;
alter table public.lojas      enable row level security;
alter table public.inscricoes enable row level security;
alter table public.avisos     enable row level security;

drop policy if exists "produtos publicos" on public.produtos;
create policy "produtos publicos" on public.produtos for select to anon, authenticated using (ativo);

drop policy if exists "ofertas publicas" on public.ofertas;
create policy "ofertas publicas" on public.ofertas for select to anon, authenticated using (true);

drop policy if exists "lojas publicas" on public.lojas;
create policy "lojas publicas" on public.lojas for select to anon, authenticated using (true);

-- ---------------------------------------------------------------------
-- Funções chamadas pelo site
-- ---------------------------------------------------------------------
create or replace function public.normaliza(t text) returns text
language sql immutable as $$
  select trim(regexp_replace(lower(translate(coalesce(t,''),
    'áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ',
    'aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN')), '[^a-z0-9]+', ' ', 'g'))
$$;

create or replace function public.criar_alerta(
  p_categoria text, p_marca text, p_nome text, p_cor text,
  p_foto_url text, p_link text,
  p_pessoa text, p_email text, p_whatsapp text, p_callmebot text
) returns json
language plpgsql security definer set search_path = public as $$
declare
  v_chave text;
  v_prod  uuid;
  v_email text := nullif(lower(trim(coalesce(p_email,''))), '');
  v_wpp   text := nullif(regexp_replace(coalesce(p_whatsapp,''), '[^0-9]', '', 'g'), '');
  v_key   text := nullif(trim(coalesce(p_callmebot,'')), '');
  v_link  text := nullif(trim(coalesce(p_link,'')), '');
  v_token uuid;
begin
  if coalesce(trim(p_marca),'') = '' or coalesce(trim(p_nome),'') = '' then
    raise exception 'Informe a marca e o nome do produto.';
  end if;
  if length(p_marca) > 80 or length(p_nome) > 160 or length(coalesce(p_cor,'')) > 80 then
    raise exception 'Texto muito longo.';
  end if;
  if v_email is null and v_wpp is null then
    raise exception 'Informe um e-mail ou WhatsApp.';
  end if;
  if v_email is not null and v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
    raise exception 'E-mail inválido.';
  end if;
  if v_wpp is not null and (length(v_wpp) < 10 or length(v_wpp) > 15) then
    raise exception 'WhatsApp inválido. Use DDD + número.';
  end if;
  if v_link is not null and v_link !~* '^https?://' then
    raise exception 'O link precisa começar com http:// ou https://';
  end if;
  if v_wpp is not null and length(v_wpp) <= 11 then v_wpp := '55' || v_wpp; end if;

  -- limite anti-abuso
  if (select count(*) from inscricoes
      where ativo and ((v_email is not null and email = v_email) or (v_wpp is not null and whatsapp = v_wpp))) >= 30 then
    raise exception 'Você já tem 30 alertas ativos. Cancele algum para criar outro.';
  end if;

  v_chave := normaliza(p_marca) || '|' || normaliza(p_nome) || '|' || normaliza(p_cor);

  insert into produtos (categoria, marca, nome, cor, foto_url, links, chave)
  values (coalesce(nullif(trim(p_categoria),''),'Outro'), trim(p_marca), trim(p_nome),
          nullif(trim(coalesce(p_cor,'')),''), nullif(trim(coalesce(p_foto_url,'')),''),
          case when v_link is null then '{}' else array[v_link] end, v_chave)
  on conflict (chave) do update set
    ativo    = true,
    foto_url = coalesce(produtos.foto_url, excluded.foto_url),
    links    = case when v_link is null or v_link = any(produtos.links) then produtos.links
                    else produtos.links || v_link end
  returning id into v_prod;

  select token into v_token from inscricoes
   where produto_id = v_prod and ativo
     and ((v_email is not null and email = v_email) or (v_wpp is not null and whatsapp = v_wpp))
   limit 1;

  if v_token is null then
    insert into inscricoes (produto_id, nome, email, whatsapp, callmebot_key)
    values (v_prod, nullif(trim(coalesce(p_pessoa,'')),''), v_email, v_wpp, v_key)
    returning token into v_token;
  else
    update inscricoes set callmebot_key = coalesce(v_key, callmebot_key),
                          email = coalesce(v_email, email),
                          whatsapp = coalesce(v_wpp, whatsapp)
     where token = v_token;
  end if;

  return json_build_object('produto_id', v_prod, 'token', v_token);
end $$;

create or replace function public.cancelar_alerta(p_token uuid) returns boolean
language plpgsql security definer set search_path = public as $$
declare v_prod uuid;
begin
  update inscricoes set ativo = false where token = p_token returning produto_id into v_prod;
  if v_prod is null then return false; end if;
  -- produto sem ninguém esperando sai da vitrine
  if not exists (select 1 from inscricoes where produto_id = v_prod and ativo) then
    update produtos set ativo = false where id = v_prod;
  end if;
  return true;
end $$;

create or replace function public.estatisticas() returns json
language sql security definer set search_path = public as $$
  select json_build_object(
    'produtos',  (select count(*) from produtos where ativo),
    'alertas',   (select count(*) from inscricoes where ativo),
    'avisos',    (select count(*) from avisos where ok),
    'lojas',     (select count(*) from lojas),
    'catalogo',  (select count(*) from catalogo)
  )
$$;

revoke all on function public.criar_alerta(text,text,text,text,text,text,text,text,text,text) from public;
grant execute on function public.criar_alerta(text,text,text,text,text,text,text,text,text,text) to anon, authenticated;
grant execute on function public.cancelar_alerta(uuid) to anon, authenticated;
grant execute on function public.estatisticas() to anon, authenticated;

-- ---------------------------------------------------------------------
-- Fotos enviadas pelo site (Storage público, só imagens até 5 MB)
-- ---------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('fotos', 'fotos', true, 5242880, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public = true, file_size_limit = 5242880,
  allowed_mime_types = array['image/jpeg','image/png','image/webp'];

drop policy if exists "upload de fotos" on storage.objects;
create policy "upload de fotos" on storage.objects for insert to anon, authenticated
  with check (bucket_id = 'fotos');
