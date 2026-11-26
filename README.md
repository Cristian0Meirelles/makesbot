# 💄 Voltou! — bot de reposição de maquiagem

Site + bot que fica de olho nas lojas 24h e avisa por **e-mail** e **WhatsApp** quando uma maquiagem esgotada volta ao estoque, com o link direto do produto (e o seu link de afiliado, se tiver).

**Tudo grátis**: GitHub Actions (bot), GitHub Pages (site), Supabase (banco), Gmail (e-mail) e CallMeBot (WhatsApp).

| O que roda | Quando |
|---|---|
| Radar de estoque: todas as lojas + links colados | a cada 5 min |
| Links do TikTok Shop + catálogo de maquiagem de todas as lojas do TikTok Shop | 2x por dia (09h e 21h) |
| Catálogo do autocompletar (pega lançamentos sozinho) | 1x por dia (04h) |
| Religar agendamentos (o GitHub desliga após 60 dias parado) | toda semana |

O bot **só manda mensagem quando o produto volta** (passa de esgotado para disponível). Se ele piscar (esgota e volta logo), não repete o aviso da mesma loja para a mesma pessoa antes de 12h.

---

## Instalação (uns 20 minutos, uma vez só)

### 1. Banco de dados: Supabase
1. Crie uma conta em **https://supabase.com** → **New project** (região: *South America (São Paulo)*). Guarde a senha.
2. No menu da esquerda: **SQL Editor** → **New query** → cole todo o arquivo [`supabase/schema.sql`](supabase/schema.sql) → **Run**.
3. Vá em **Project Settings → API** (ou *Data API / API Keys*) e copie:
   - **Project URL** (ex.: `https://abcd.supabase.co`)
   - chave **anon / public**
   - chave **service_role / secret** ⚠️ essa é secreta, só vai no GitHub Secrets

### 2. E-mail: senha de app do Gmail
1. Use um Gmail só para o bot (recomendado), ex.: `voltou.alertas@gmail.com`.
2. Ative a **verificação em 2 etapas** na conta Google.
3. Acesse **https://myaccount.google.com/apppasswords** → crie uma senha com o nome `Voltou` → copie os 16 caracteres.
   O Gmail grátis envia até ~500 e-mails por dia.

### 3. Segredos no GitHub
No repositório: **Settings → Secrets and variables → Actions**.

Aba **Secrets** → *New repository secret*:

| Nome | Valor |
|---|---|
| `SUPABASE_URL` | Project URL do Supabase |
| `SUPABASE_SERVICE_KEY` | chave **service_role** |
| `SMTP_USER` | o Gmail do bot |
| `SMTP_PASSWORD` | a senha de app de 16 letras |
| `ADMIN_EMAIL` *(opcional)* | seu e-mail, para receber cópia de todo "voltou" |
| `ADMIN_WHATSAPP` *(opcional)* | seu WhatsApp, ex.: `5511999999999` |
| `ADMIN_CALLMEBOT_KEY` *(opcional)* | sua chave CallMeBot (passo 6) |

Aba **Variables** → *New repository variable*:

| Nome | Valor |
|---|---|
| `SITE_URL` | `https://cristian0meirelles.github.io/makesbot` |

### 4. Ligar o site no ar
1. Edite o arquivo [`docs/config.js`](docs/config.js) aqui no GitHub (ícone de lápis) e preencha `supabaseUrl` e `supabaseAnonKey` (a chave **anon**, nunca a service_role). → *Commit changes*.
2. **Settings → Pages** → *Source: Deploy from a branch* → Branch **main**, pasta **/docs** → *Save*.
3. Em 1–2 minutos o site está em **https://cristian0meirelles.github.io/makesbot**

### 5. Testar
1. Aba **Actions** → se pedir, clique em *I understand… enable workflows*.
2. Rode **Testar lojas e avisos** (*Run workflow*), colocando seu e-mail (e WhatsApp + chave, se já tiver). O resultado mostra quais lojas responderam ✅ e se o e-mail chegou.
3. Rode **Catálogo (1x por dia)** uma vez na mão, para já encher o autocompletar.
4. Crie um alerta pelo site para um produto que **está disponível**. No próximo ciclo (até 5–10 min) o aviso deve chegar.

### 6. WhatsApp (grátis via CallMeBot)
Cada pessoa ativa uma vez, direto no formulário do site:
1. Toca em **Ativar no WhatsApp** → envia a mensagem pronta para o robô.
2. Recebe uma **APIKEY** e cola no formulário.

Pronto, ela passa a receber os avisos. Faça isso com o seu número também e coloque a chave em `ADMIN_CALLMEBOT_KEY`.

> O CallMeBot é gratuito e pensado para uso pessoal. Se o site crescer muito (centenas de pessoas), o próximo passo é a **API oficial do WhatsApp (Meta)**: a Meta dá um número grátis, mas cada aviso custa alguns centavos. O bot já suporta: preencha `META_WA_TOKEN`, `META_WA_PHONE_ID` (secrets) e `META_WA_TEMPLATE` (variable).

---

## Ajustes

### Lojas e links de afiliado → [`config/lojas.yaml`](config/lojas.yaml)
- Adicione ou remova lojas (`tipo: auto` descobre sozinho se é VTEX ou Shopify).
- Coloque seu modelo de afiliado em `afiliado:` usando `{url}` ou `{url_enc}`:
  - **Awin** (Sephora, Beleza na Web, Época e outras): `https://www.awin1.com/cread.php?awinmid=ID_DA_LOJA&awinaffid=SEU_ID&ued={url_enc}`
  - **Amazon**: `{url}?tag=SEUTAG-20`
  - **Mercado Livre**: pegue os parâmetros no painel de afiliados do ML.
- No Mercado Livre, `somente_oficial: true` ignora revendedores (que costumam vender mais caro).

### Checagem exatamente a cada 5 minutos (opcional)
O agendamento grátis do GitHub às vezes atrasa alguns minutos em horário de pico. Se quiser precisão:
1. Crie um token em **GitHub → Settings → Developer settings → Fine-grained tokens** com permissão *Actions: Read and write* só neste repositório.
2. Em **https://cron-job.org** (grátis), crie um job a cada 5 min:
   - URL: `https://api.github.com/repos/Cristian0Meirelles/makesbot/actions/workflows/radar.yml/dispatches`
   - Método **POST**, corpo `{"ref":"main"}`
   - Headers: `Authorization: Bearer SEU_TOKEN`, `Accept: application/vnd.github+json`

---

## Como funciona por dentro

```
site (docs/)  ──cadastro──▶  Supabase  ◀──lê/grava──  bot (GitHub Actions)
   ▲                         produtos, inscrições,        │
   └──── catálogo / ofertas ─ ofertas, catálogo ◀──────────┘
                                                          │ voltou?
                                                          ▼
                                                 e-mail + WhatsApp
```

- **`bot/lojas.py`**: lê as lojas. VTEX (API pública de catálogo, mostra o estoque de cada cor), Shopify (`suggest.json` e `products.json`), Mercado Livre (página de busca), links de qualquer site (dados *schema.org* da página) e TikTok Shop (experimental).
- **`bot/matcher.py`**: confere se o resultado é mesmo o produto (marca + nome + cor; ignora kits, refis e miniaturas).
- **`bot/motor.py`**: compara com a última checagem e só avisa na virada esgotado → disponível.
- **`bot/catalogo.py`**: monta o catálogo diário do autocompletar.
- **`bot/notificar.py`**: e-mail HTML bonito + WhatsApp, com link para cancelar.

Rodar no seu PC (opcional): `pip install -r requirements.txt` e depois `python -m bot.main testar` ou `python -m bot.main rapido --seco` (sem enviar nada).

## Limitações (sendo honesto)
- **Lojas que funcionam na busca automática** (teste de 25/11/2026): Época Cosméticos, Amo Beleza, Pague Menos, Lojas Americanas, Océane, Mari Maria Makeup, Dailus, Catharine Hill e Hinode.
- **Sephora, Beleza na Web, MAC, Boticário, QDB, Natura, Vult e outras bloqueiam robôs** (respondem 403 para servidores). O bot respeita o bloqueio e não tenta burlar. O caminho certo para elas é o **feed de produtos do programa de afiliados** (Awin, Lomadee etc.), que traz preço e estoque de forma oficial, e você ainda ganha a comissão. Dá pra plugar depois.
- **Mercado Livre** não entrega a página de busca para servidores. A forma oficial é a API do Mercado Livre com um app de desenvolvedor (grátis); dá pra adicionar depois.
- **TikTok Shop** bloqueia robôs com frequência. Por isso só checamos 2x por dia. Além dos links colados, o bot abre as categorias de maquiagem do TikTok Shop num navegador (`bot/tiktok_catalogo.py`, configurado em `tiktok_catalogo` no `config/lojas.yaml`) e põe no catálogo os produtos de todas as lojas que aparecem lá. O site do TikTok mostra no máximo ~100 produtos por categoria, então não é tudo. Como o TikTok costuma bloquear os servidores do GitHub, dá pra rodar o mesmo robô **no seu PC, abrindo o seu Google Chrome**: veja `robo-tiktok/LEIA-ME.txt`. Se aparecer a verificação (CAPTCHA), o bot para, guarda o que já pegou e não tenta burlar; o estado não muda (ninguém recebe aviso falso).
- **Sites de marca** que não são VTEX/Shopify (o teste mostra ❌) só são monitorados pelos **links** que as pessoas colam. Funciona com qualquer página de produto que publique os dados padrão de produto (a maioria publica).
- **Amazon** bloqueia robôs; cole o link e o bot tenta, mas pode não funcionar.
- O bot nunca compra nada: ele manda o link, e a pessoa compra.

---

© 2026 Cristiano Cotrin Meirelles. Todos os direitos reservados. Código proprietário, veja [LICENSE](LICENSE). Proibido copiar, modificar, redistribuir ou vender sem autorização por escrito do autor.
