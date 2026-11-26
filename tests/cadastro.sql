-- Executar após instalar o esquema em banco descartável.
begin;
set local role anon;
do $$
declare resposta json;
begin
  select public.criar_alerta('Batom','Marca QA','Produto QA','cor',null,null,
                             'Teste','qa@example.invalid',null,null) into resposta;
  if resposta::jsonb ? 'token' then raise exception 'Token exposto ao público'; end if;
  perform public.criar_alerta('Batom','Marca QA','Produto QA','cor',null,null,
                              'Repetido','qa@example.invalid','11900000000','chave-ficticia');
end $$;
reset role;
do $$
begin
  if (select count(*) from public.inscricoes where email='qa@example.invalid') <> 1
     or exists (select 1 from public.inscricoes where email='qa@example.invalid'
                and (whatsapp is not null or callmebot_key is not null)) then
    raise exception 'Cadastro repetido alterou ou duplicou a inscrição';
  end if;
end $$;
rollback;
