-- Atualiza a função pública de cadastro sem modificar inscrições existentes.
begin;
create or replace function public.criar_alerta(
  p_categoria text, p_marca text, p_nome text, p_cor text,
  p_foto_url text, p_link text,
  p_pessoa text, p_email text, p_whatsapp text, p_callmebot text
) returns json
language plpgsql security definer set search_path = pg_catalog, public, pg_temp as $$
declare
  v_chave text;
  v_prod  uuid;
  v_email text := nullif(lower(trim(coalesce(p_email,''))), '');
  v_wpp   text := nullif(regexp_replace(coalesce(p_whatsapp,''), '[^0-9]', '', 'g'), '');
  v_key   text := nullif(trim(coalesce(p_callmebot,'')), '');
  v_link  text := nullif(trim(coalesce(p_link,'')), '');

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

  -- O cadastro público nunca altera uma inscrição existente.
  if not exists (
    select 1 from inscricoes where produto_id = v_prod and ativo
    and ((v_email is not null and email = v_email) or (v_wpp is not null and whatsapp = v_wpp))
  ) then
    insert into inscricoes (produto_id, nome, email, whatsapp, callmebot_key)
    values (v_prod, nullif(trim(coalesce(p_pessoa,'')),''), v_email, v_wpp, v_key);
  end if;
  return json_build_object('produto_id', v_prod);
end $$;

revoke all on function public.criar_alerta(text,text,text,text,text,text,text,text,text,text) from public;
grant execute on function public.criar_alerta(text,text,text,text,text,text,text,text,text,text) to anon, authenticated;
commit;
