(() => {
"use strict";
const C = window.VOLTOU_CONFIG || {};
const DEMO = !(C.supabaseUrl && C.supabaseAnonKey);
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const norm = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const toks = s => norm(s).split(" ").filter(t => t.length > 1 || /\d/.test(t));
const brl = v => v ? Number(v).toLocaleString("pt-BR", {style:"currency", currency:"BRL"}) : "";
const urlSegura = u => /^https?:\/\//i.test(u || "") ? u : "#";
const tempo = iso => { if (!iso) return ""; const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 2 ? "agora mesmo" : m < 60 ? `há ${m} min` : m < 1440 ? `há ${Math.round(m/60)} h` : `há ${Math.round(m/1440)} dia(s)`; };

const CATEGORIAS = ["Blush","Batom","Gloss","Lip tint","Lápis labial","Base","Corretivo","Pó","Iluminador","Bronzer","Contorno","Sombra","Máscara de cílios","Delineador","Sobrancelha","Primer","Fixador","Outro"];
const MARCAS = ["MAC","Fenty Beauty","Rare Beauty","Charlotte Tilbury","NARS","Dior","Benefit","Too Faced","Huda Beauty","Urban Decay","Clinique","Lancôme","Estée Lauder","Make Up For Ever","Sephora Collection","Bruna Tavares","Boca Rosa Beauty","Mari Maria Makeup","Vult","Ruby Rose","Quem Disse, Berenice?","Océane","Natura","Eudora","Boticário","Make B.","Payot","Dailus","Fran by Franciny Ehlke","Melu","Tracta","Max Love","Catharine Hill","Hinode"];

/* ------------------------------------------------ fotos (sempre reais; sem foto = aviso neutro) */
const corDe = () => "";
const semFoto = tam => `<div class="sem-foto" style="font-size:${tam < 60 ? 0 : 12}px"><svg width="${Math.max(18, tam / 4)}" height="${Math.max(18, tam / 4)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="6" width="18" height="13" rx="3"/><circle cx="12" cy="12.5" r="3.2"/><path d="M8 6l1.5-2h5L16 6"/></svg>${tam >= 60 ? "<span>sem foto</span>" : ""}</div>`;
function fotosValidas(urls) {
  return [...new Set(urls.filter(u => typeof u === "string" && /^https?:\/\//i.test(u)).map(u => u.replace(/^http:/i, "https:")))];
}
function fotoNoTamanho(url, tam) {
  const foto = new URL(url);
  if (foto.hostname === "sdcdn.io" && foto.searchParams.has("width")) {
    const largura = tam >= 200 ? 900 : tam >= 100 ? 560 : 120;
    foto.searchParams.set("width", largura);
    foto.searchParams.set("height", largura);
  }
  return foto.href;
}
function fotoOu(img, _cat, _cor, tam = 120, alternativas = [], grupo = "") {
  const fotos = fotosValidas([img, ...alternativas]).map(url => fotoNoTamanho(url, tam));
  return fotos.length ? `<img src="${esc(fotos[0])}" alt="" loading="${tam >= 200 ? "eager" : "lazy"}" decoding="async" referrerpolicy="no-referrer" data-foto-tam="${tam}" data-alternativas="${esc(JSON.stringify(fotos.slice(1)))}" data-grupo="${esc(grupo)}" data-cor="${esc(_cor || "")}">` : semFoto(tam);
}
document.addEventListener("error", async event => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement)) return;
  if (img.hasAttribute("data-foto-tam")) {
    let alternativas = JSON.parse(img.dataset.alternativas || "[]");
    if (!alternativas.length && img.dataset.grupo) {
      const grupo = img.dataset.grupo;
      delete img.dataset.grupo;
      try {
        const linhas = await linhasDoGrupo(grupo);
        alternativas = fotosValidas(linhas.filter(r => !img.dataset.cor || norm(r.cor) === norm(img.dataset.cor)).map(r => r.imagem)).map(u => fotoNoTamanho(u, Number(img.dataset.fotoTam))).filter(u => u !== img.src);
      } catch {}
    }
    if (alternativas.length) {
      img.src = alternativas.shift();
      img.dataset.alternativas = JSON.stringify(alternativas);
    } else img.outerHTML = semFoto(Number(img.dataset.fotoTam) || 120);
  }
  else if (img.hasAttribute("data-iniciais")) img.replaceWith(document.createTextNode(img.dataset.iniciais));
  else if (img.hasAttribute("data-remover")) img.remove();
}, true);

/* ------------------------------------------------ demonstração: produtos REAIS de docs/demo.json */
let DEMO_DADOS = null;
async function carregarDemo() {
  if (DEMO_DADOS) return DEMO_DADOS;
  try { DEMO_DADOS = await (await fetch("demo.json", {cache: "no-cache"})).json(); }
  catch (e) { console.warn("demo.json", e); DEMO_DADOS = {lojas: [], catalogo: []}; }
  return DEMO_DADOS;
}
function demoCatalogo() { return (DEMO_DADOS && DEMO_DADOS.catalogo) || []; }
function demoRadar() {
  // monta a vitrine com produtos reais do catálogo (um por grupo, vários tipos)
  const grupos = new Map();
  for (const r of demoCatalogo()) { const g = grupos.get(r.grupo) || []; g.push(r); grupos.set(r.grupo, g); }
  const usadas = new Set(), saida = [];
  const lista = [...grupos.values()].filter(g => g.some(r => r.imagem)).sort((a, b) => b.length - a.length);
  for (const g of lista) {
    const ref = g.find(r => r.imagem && r.cor) || g.find(r => r.imagem);
    if (usadas.has(ref.categoria) && saida.length < 6) continue;
    usadas.add(ref.categoria);
    const doTom = g.filter(r => norm(r.cor) === norm(ref.cor));
    saida.push({id: ref.grupo, categoria: ref.categoria, marca: ref.marca || "", nome: ref.produto, cor: ref.cor,
      disponivel: doTom.some(r => r.disponivel), imagem_loja: ref.imagem, foto_url: null, criado_em: ref.atualizado_em,
      disponivel_desde: ref.atualizado_em, ofertas: doTom.map(r => ({loja: r.loja, preco: r.preco, disponivel: r.disponivel, url: r.url, url_afiliado: r.url_afiliado, imagem: r.imagem, atualizado_em: r.atualizado_em}))});
    if (saida.length >= 12) break;
  }
  return saida;
}

/* ------------------------------------------------ acesso ao Supabase */
async function api(caminho, {method = "GET", body, headers = {}} = {}) {
  const r = await fetch(`${C.supabaseUrl.replace(/\/$/, "")}/rest/v1/${caminho}`, {
    method, headers: {apikey: C.supabaseAnonKey, Authorization: `Bearer ${C.supabaseAnonKey}`, "Content-Type": "application/json", ...headers},
    body: body ? JSON.stringify(body) : undefined,
  });
  const txt = await r.text();
  const dado = txt ? JSON.parse(txt) : null;
  if (!r.ok) throw new Error((dado && (dado.message || dado.hint)) || `Erro ${r.status}`);
  return dado;
}
const rpc = (nome, args) => api(`rpc/${nome}`, {method: "POST", body: args});

let LOJAS = [], RADAR = [];
const dominioDe = loja => (LOJAS.find(l => l.nome === loja) || {}).dominio || "";
function logoLoja(loja) {
  const d = dominioDe(loja), ini = esc((loja || "?").replace(/[^A-Za-zÀ-ú0-9]/g, "").slice(0, 2).toUpperCase());
  return `<div class="logo-loja">${d ? `<img src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(d)}&sz=64" alt="" data-iniciais="${ini}">` : ini}</div>`;
}

async function buscarCatalogo(termo, limite = 400) {
  const ts = toks(termo).slice(0, 6);
  if (!ts.length) return [];
  if (DEMO) { await carregarDemo(); return demoCatalogo().filter(r => ts.every(t => (r.busca || "").includes(t))); }
  const filtro = ts.map(t => `busca.imatch.[[:<:]]${t}[[:>:]]`).join(",");
  return api(`catalogo?select=${CAMPOS}&and=(${encodeURIComponent(filtro)})&order=disponivel.desc,preco.asc.nullslast&limit=${limite}`);
}

const q = $("#q");
const sugestoes = $("#sugestoes");
let timerSugestoes, pedidoSugestoes;

function fecharSugestoes() {
  clearTimeout(timerSugestoes);
  pedidoSugestoes?.abort();
  sugestoes.classList.remove("on");
  sugestoes.replaceChildren();
}

function permitePrefixo(palavras, i) {
  return i === palavras.length - 1 && palavras[i] !== "mac";
}
function filtroDeBusca(palavras) {
  return palavras.map((p, i) => `busca.imatch.[[:<:]]${p}${permitePrefixo(palavras, i) ? "" : "[[:>:]]"}`).join(",");
}
function correspondeNaDemo(v, palavras) {
  const texto = norm(v.busca).split(" ");
  return palavras.every((p, i) => texto.some(t => permitePrefixo(palavras, i) ? t.startsWith(p) : t === p));
}
async function pesquisarOfertas(palavras, filtros, signal, previa = false) {
  const aceita = r => (!filtros.tipo || r.categoria === filtros.tipo) && (!filtros.marca || r.marca === filtros.marca)
    && (!filtros.disp || r.disponivel) && (!filtros.lojas?.length || filtros.lojas.includes(r.loja))
    && (!filtros.tons?.length || filtros.tons.includes(r.tom)) && (!filtros.cores?.length || filtros.cores.includes(r.familia));
  let linhas = [];
  if (DEMO) {
    await carregarDemo();
    linhas = demoCatalogo().filter(r => aceita(r) && correspondeNaDemo(r, palavras));
  } else {
    const p = new URLSearchParams({select: CAMPOS, and: "(" + filtroDeBusca(palavras) + ")",
      categoria: "neq.Outro", order: "grupo.asc,id.asc", limit: previa ? "100" : "1000"});
    if (filtros.tipo) p.set("categoria", "eq." + filtros.tipo);
    if (filtros.marca) p.set("marca", "eq." + filtros.marca);
    if (filtros.disp) p.set("disponivel", "eq.true");
    for (let offset = 0;;) {
      p.set("offset", offset);
      const r = await fetch(C.supabaseUrl + "/rest/v1/catalogo?" + p, {
        headers: {apikey: C.supabaseAnonKey, Authorization: "Bearer " + C.supabaseAnonKey}, signal});
      if (!r.ok) throw new Error("Busca indisponível");
      const lote = await r.json();
      linhas.push(...lote.filter(aceita));
      if (lote.length < Number(p.get("limit"))) break;
      if (previa && new Set(linhas.map(r => r.grupo)).size > 6) {
        const ultimo = lote[lote.length - 1].grupo;
        linhas = linhas.filter(r => r.grupo !== ultimo);
        break;
      }
      offset += lote.length;
    }
  }
  const grupos = new Map();
  for (const r of linhas) {
    const chave = r.grupo;
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(r);
  }
  return [...grupos.values()].flatMap(ofertas => {
    const [item] = agregarDemo(ofertas);
    if (!item) return [];
    const cores = new Set(ofertas.map(r => r.cor));
    return [{...item, linhasBuscadas: ofertas, corBuscada: cores.size === 1 ? ofertas[0].cor : null}];
  });
}
async function preverProdutos(termo, signal) {
  const palavras = toks(termo);
  return ordenar(await pesquisarOfertas(palavras, {}, signal, true)).slice(0, 6);
}

function agendarSugestoes() {
  fecharSugestoes();
  const termo = q.value.trim();
  if (!toks(termo).length || termo.length < 2) return;
  const pedido = new AbortController();
  pedidoSugestoes = pedido;
  timerSugestoes = setTimeout(async () => {
    let itens;
    try { itens = await preverProdutos(termo, pedido.signal); }
    catch { return; }
    if (pedido.signal.aborted || document.activeElement !== q) return;
    sugestoes.innerHTML = itens.map(v => `
      <button type="button" class="sug">
        <span class="mini">${fotoOu(v.imagem, v.categoria, "", 46)}</span>
        <span><b class="t">${esc(v.nome)}</b><br><span class="s">${esc(v.marca)}${v.preco_min ? " · " + brl(v.preco_min) : ""}</span></span>
        <span class="st">${v.disponivel ? "Tem" : "Esgotado"}</span>
      </button>`).join("") + `<button type="button" class="ver-todos">Pesquisar “${esc(termo)}” no catálogo →</button>`;
    sugestoes.querySelectorAll(".sug").forEach((botao, i) => {
      botao.onclick = () => { fecharSugestoes(); abrirProduto(itens[i]); };
    });
    sugestoes.querySelector(".ver-todos").onclick = buscarNoCatalogo;
    sugestoes.classList.add("on");
  }, 240);
}
q.addEventListener("input", agendarSugestoes);
q.addEventListener("focus", agendarSugestoes);
$("#busca").addEventListener("focusout", e => {
  if (!$("#busca").contains(e.relatedTarget)) fecharSugestoes();
});
$("#busca").addEventListener("keydown", e => {
  if (e.key === "Escape") { q.focus(); fecharSugestoes(); }
});
document.addEventListener("pointerdown", e => {
  if (!$("#busca").contains(e.target)) fecharSugestoes();
});
function buscarNoCatalogo() {
  fecharSugestoes();
  Object.assign(F, filtrosIniciais(), {busca: q.value.trim()});
  $("#fBusca").value = F.busca;
  $("#fMarca").value = "";
  $("#fDisp").checked = false;
  $("#fOrdem").value = F.ordem;
  chipsCatalogo();
  carregarCatalogo();
  $("#catalogo").scrollIntoView({behavior: "smooth"});
}
$("#btnBuscar").onclick = buscarNoCatalogo;
q.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); buscarNoCatalogo(); }
});

/* ------------------------------------------------ escolha -> tipos -> comparação */
const R = $("#resultado");
let ALVO = null;
const alvo = () => ALVO || R;
const CAMPOS = "loja,marca,produto,cor,categoria,titulo,url,url_afiliado,imagem,preco,disponivel,grupo,familia,tom,atualizado_em";

async function linhasDoGrupo(grupo) {
  if (DEMO) { await carregarDemo(); return demoCatalogo().filter(r => r.grupo === grupo); }
  const linhas = [];
  for (;;) {
    const lote = await api(`catalogo?select=${CAMPOS}&grupo=eq.${encodeURIComponent(grupo)}&order=id.asc&offset=${linhas.length}&limit=500`);
    linhas.push(...lote);
    if (lote.length < 500) return linhas;
  }
}

let OFICIAIS = null;
async function carregarOficiais() {
  if (OFICIAIS) return OFICIAIS;
  try { OFICIAIS = (await (await fetch("oficiais.json", {cache: "no-cache"})).json()).marcas || []; } catch { OFICIAIS = []; }
  return OFICIAIS;
}
function linkProduto(valor) {
  try {
    const url = new URL(valor);
    return url.protocol === "https:" && url.pathname.replace(/\//g, "").length > 0;
  } catch { return false; }
}
function oficialDe(marca) {
  const m = norm(marca);
  if (!m || !OFICIAIS) return null;
  return OFICIAIS.find(o => [o.marca, ...(o.apelidos || [])].some(a => norm(a) === m)) || null;
}
const SELO_OFICIAL = '<span class="selo-oficial">✓ Site oficial</span>';
let tomFiltro = "";
const corFalsa = c => !c || /^(\d+([.,]\d+)?\s*(un|und|unid|unidade|unidades|ml|g|gr|kg|oz)?|unic[oa]|padr[aã]o|u|default|default title|sem cor)$/i.test(String(c).trim());
async function abrirComparacao(g, cat, corEscolhida) {
  g.linhas.forEach(r => { if (corFalsa(r.cor)) r.cor = null; });
  const base = g.tipo === "produto" ? g.linhas : g.linhas.filter(r => (r.categoria || "Outro") === cat);
  const ref = base[0];
  // todas as cores do mesmo produto, em todas as lojas
  let todas = base;
  try {
    if (!ref.grupo) {
      const mais = await buscarCatalogo(`${ref.marca || ""} ${ref.produto}`, 600), tp = toks(ref.produto);
      todas = mais.filter(r => (r.categoria || "Outro") === cat && tp.every(t => norm(r.produto).includes(t)));
    }
    if (!todas.length) todas = base;
  } catch (e) { console.warn(e); }
  todas.forEach(r => { if (corFalsa(r.cor)) r.cor = null; });

  const cores = new Map();
  const temCores = todas.some(r => r.cor);
  for (const r of todas) {
    if (!r.cor && temCores) continue;          // loja sem cor (ex.: TikTok): aparece em todas as cores
    const k = norm(r.cor) || "_";
    const c = cores.get(k) || {nome: r.cor || "Única", img: null, disp: false, tom: r.tom || ""};
    c.img ||= r.imagem; c.disp ||= r.disponivel; cores.set(k, c);
  }
  const tons = [...new Set([...cores.values()].map(c => c.tom).filter(Boolean))].sort();
  let corAtual = corEscolhida ?? (g.tipo === "cor" ? norm(g.rotulo) : null);
  if (!corAtual || !cores.has(corAtual)) {   // começa na cor mais barata disponível
    const comCor = todas.filter(r => r.cor || !temCores);
    const melhor = comCor.filter(r => r.disponivel && r.preco).sort((a, b) => a.preco - b.preco)[0] || comCor[0] || todas[0];
    corAtual = norm(melhor.cor) || "_";
  }
  const linhas = todas.filter(r => (norm(r.cor) || "_") === corAtual);
  const porLoja = new Map();
  for (const r of linhas) { const a = porLoja.get(r.loja); if (!a || (r.disponivel && !a.disponivel) || (r.disponivel === a.disponivel && (r.preco || 1e9) < (a.preco || 1e9))) porLoja.set(r.loja, r); }
  const lista = [...porLoja.values()].sort((a, b) => (b.disponivel - a.disponivel) || ((a.preco || 1e9) - (b.preco || 1e9)));
  let disp = lista.filter(r => r.disponivel); const corNome = cores.get(corAtual)?.nome || "";
  let melhorLoja = disp.filter(r => r.preco).sort((a, b) => a.preco - b.preco)[0];
  const img = lista.find(r => r.imagem)?.imagem || cores.get(corAtual)?.img;
  const pendentes = ["Mercado Livre", "TikTok Shop"].filter(loja => !porLoja.has(loja));
  const nomeProduto = g.nome || ref.produto;
  await carregarOficiais();
  const oficial = oficialDe(ref.marca);

  const outras = new Map();
  for (const r of todas) {
    if (porLoja.has(r.loja)) continue;
    const anterior = outras.get(r.loja);
    if (!anterior || (r.disponivel && !anterior.disponivel)) outras.set(r.loja, r);
  }
  const oficialDoProduto = oficial && !porLoja.has(oficial.loja) && !outras.has(oficial.loja) && oficial.produtos?.[ref.grupo];
  const coresVisiveis = [...cores].filter(([k, c]) => !tomFiltro || c.tom === tomFiltro || k === corAtual);

  alvo().innerHTML = `<div class="painel">
    <div class="passos"><b>${esc(g.rotulo)}</b><span class="sep">›</span>${g.cats.size > 1 ? `<button id="voltarTipos">${esc(cat)}</button>` : `<span>${esc(cat)}</span>`}<span class="sep">›</span><span>Preços e estoque</span></div>
    <div class="comparar">
      <div><div class="foto-grande">${fotoOu(img, cat, "", 220, linhas.map(r => r.imagem))}<span class="pill ${disp.length ? "on" : "off"}">${disp.length ? "Disponível agora" : "Esgotado"}</span></div></div>
      <div>
        <div class="marca">${esc(ref.marca || "")} · ${esc(cat)}</div>
        <h2>${esc(nomeProduto)}</h2>
        <div class="resumo">${corNome && corNome !== "Única" ? `Cor <b style="color:var(--tinta)">${esc(corNome)}</b> · ` : ""}${melhorLoja ? `<b>Melhor preço: ${brl(melhorLoja.preco)}</b> na ${esc(melhorLoja.loja)} · ` : ""}${disp.length ? `tem em ${disp.length} de ${lista.length} loja${lista.length > 1 ? "s" : ""}` : "esgotado nas ofertas verificadas"}</div>
        ${cores.size > 1 ? `<div class="cores-titulo">Cores (${cores.size})</div>
          ${tons.length > 1 ? `<div class="tons-filtro">${["", ...tons].map(t => `<button class="chip${t === tomFiltro ? " on" : ""}" data-tom="${esc(t)}">${t ? "Pele " + esc(t).toLowerCase() : "Todos os tons"}</button>`).join("")}</div>` : ""}
          <div class="cores">${coresVisiveis.map(([k, c]) => `
          <button class="cor${k === corAtual ? " on" : ""}" data-k="${esc(k)}"><span class="bol">${c.img ? `<img src="${esc(c.img)}" alt="" loading="lazy">` : `<span style="display:grid;place-items:center;width:100%;height:100%;font-size:10px;font-weight:700">${esc((c.nome || "?").slice(0, 2).toUpperCase())}</span>`}</span>${esc(c.nome)}${c.disp ? '<span class="d" title="tem em estoque"></span>' : ""}</button>`).join("")}</div>` : ""}
        <div class="lojas-lista">${lista.map(r => `
          <div class="linha-loja${r.disponivel ? " disp" : ""}">
            ${logoLoja(r.loja)}
            <div style="min-width:0"><div class="ln">${esc(r.loja)}${oficial && r.loja === oficial.loja ? SELO_OFICIAL : ""}${r === melhorLoja && disp.length > 1 ? '<span class="selo-melhor">Melhor preço</span>' : ""}</div><div class="lt">${!r.cor && temCores ? "Várias cores · escolha a sua na loja" : esc(r.titulo)}</div>${r.atualizado_em ? `<small>Conferido ${tempo(r.atualizado_em)}</small>` : ""}</div>
            <div class="preco">${r.preco ? brl(r.preco) : "—"}<small>${r.disponivel ? '<span style="color:var(--verde)">● disponível</span>' : "esgotado"}</small></div>
            ${linkProduto(r.url) ? `<a class="btn btn-linha btn-sm" href="${esc(r.loja === oficial?.loja ? r.url : urlSegura(r.url_afiliado || r.url))}" target="_blank" rel="noopener sponsored">${r.disponivel ? "Comprar" : "Ver produto"}</a>` : "<small>Link do item pendente</small>"}
          </div>`).join("") || `<div class="vazio">Sem lojas para esta cor ainda.</div>`}
          ${outras.size ? `<h3>Outras lojas deste produto</h3>${[...outras.values()].map(r => `<div class="linha-loja">
            ${logoLoja(r.loja)}<div><div class="ln">${esc(r.loja)}${r.loja === oficial?.loja ? SELO_OFICIAL : ""}</div>
            <div>${r.cor ? "Cor " + esc(r.cor) : "Cor não informada pela loja"}</div></div>
            <div class="preco">${r.preco ? brl(r.preco) : "—"}<small>${r.disponivel ? "disponível" : "esgotado"}</small></div>
            ${linkProduto(r.url) ? `<a class="btn btn-linha btn-sm" href="${esc(r.url)}" target="_blank" rel="noopener">Ver produto</a>` : ""}</div>`).join("")}` : ""}
          ${linkProduto(oficialDoProduto) ? `<div class="linha-loja oficial">${logoLoja(oficial.loja)}
            <div><div class="ln">${esc(oficial.loja)} ${SELO_OFICIAL}</div><div class="lt">Escolha a cor na página do produto</div></div>
            <div></div><a class="btn btn-linha btn-sm" href="${esc(oficialDoProduto)}" target="_blank" rel="noopener">Ver produto</a></div>` : ""}
          </div>
        ${pendentes.length ? `<p class="atualizado">${pendentes.join(" e ")} · sem oferta confirmada para ${temCores ? "esta cor" : "este produto"}.</p>` : ""}
        <div class="acoes-produto">
          <button class="btn btn-rosa" id="btnAvisar">${disp.length ? "Me avisa se esgotar e voltar" : "Me avisa quando voltar"}</button>
        </div>
        <div class="atualizado">Cada horário indica a última consulta bem-sucedida àquela oferta. O catálogo tem atualização diária.</div>
      </div>
    </div></div>`;
  const raiz = alvo();

  raiz.querySelectorAll(".cor").forEach(b => b.onclick = () => abrirComparacao(g, cat, b.dataset.k));
  raiz.querySelectorAll("[data-tom]").forEach(b => b.onclick = () => { tomFiltro = b.dataset.tom; abrirComparacao(g, cat, corAtual); });
  raiz.querySelector("#btnAvisar").onclick = () => { fecharProduto(); preencherAlerta({categoria: cat, marca: ref.marca, nome: nomeProduto, cor: corNome === "Única" ? "" : corNome}); };
  if (corEscolhida === undefined && !ALVO) R.scrollIntoView({behavior: "smooth", block: "start"});
}

/* trava o fundo (funciona no iPhone também) */
let rolagemSalva = null;
function travarFundo() {
  if (rolagemSalva !== null) return;
  rolagemSalva = scrollY;
  Object.assign(document.body.style, {position: "fixed", top: `-${rolagemSalva}px`, left: "0", right: "0", width: "100%", overflow: "hidden"});
}
function destravarFundo() {
  if (rolagemSalva === null) return;
  Object.assign(document.body.style, {position: "", top: "", left: "", right: "", width: "", overflow: ""});
  scrollTo(0, rolagemSalva); rolagemSalva = null;
}
/* janela do produto (catálogo, busca e radar usam a mesma) */
function abrirJanela() {
  ALVO = $("#produtoCorpo");
  ALVO.innerHTML = `<div class="painel"><div class="esqueleto" style="min-height:420px"></div></div>`;
  const m = $("#modalProduto");
  if (!m.classList.contains("on")) {
    m.classList.add("on"); travarFundo();
    try { history.pushState({janela: 1}, "", location.href); } catch {}
  }
  $("#modalProduto .caixa").scrollTop = 0;
}
try { history.scrollRestoration = "manual"; } catch {}
addEventListener("popstate", () => { if ($("#modalProduto").classList.contains("on")) fecharProduto(true); });
async function abrirProduto(v) {
  abrirJanela(); tomFiltro = "";
  try {
    const grupo = await linhasDoGrupo(v.grupo);
    const linhas = grupo.filter(r => r.categoria && r.categoria !== "Outro");
    if (!linhas.length) throw new Error("sem dados");
    const g = {rotulo: v.nome, nome: v.nome, marca: v.marca, cats: new Set([v.categoria]), linhas, tipo: "produto"};
    await abrirComparacao(g, v.categoria, v.corBuscada ? norm(v.corBuscada) : null);
  } catch (e) { ALVO.innerHTML = `<div class="painel"><div class="vazio">Não consegui abrir este produto agora.</div></div>`; }
}
function fecharProduto(peloVoltar) {
  if (!$("#modalProduto").classList.contains("on")) return;
  $("#modalProduto").classList.remove("on"); destravarFundo(); ALVO = null;
  if (!peloVoltar && history.state && history.state.janela) { try { history.back(); } catch {} }
}
$("#fecharProduto").onclick = () => fecharProduto();
$("#modalProduto").onclick = e => { if (e.target.id === "modalProduto") fecharProduto(); };
addEventListener("keydown", e => { if (e.key === "Escape") fecharProduto(); });

/* ------------------------------------------------ produto que não temos */
const PISTAS_CAT = [["lip tint","Lip tint"],["tint","Lip tint"],["gloss","Gloss"],["lapis de boca","Lápis labial"],["lapis labial","Lápis labial"],["batom","Batom"],["blush","Blush"],["iluminador","Iluminador"],["bronzer","Bronzer"],["contorno","Contorno"],["corretivo","Corretivo"],["primer","Primer"],["fixador","Fixador"],["base","Base"],["po","Pó"],["paleta","Sombra"],["sombra","Sombra"],["mascara","Máscara de cílios"],["rimel","Máscara de cílios"],["delineador","Delineador"],["sobrancelha","Sobrancelha"]];
function pedirProduto(termo) {
  const t = " " + norm(termo) + " ";
  const marca = [...MARCAS].sort((a, b) => b.length - a.length).find(m => t.includes(" " + norm(m) + " ")) || "";
  const cat = (PISTAS_CAT.find(([p]) => t.includes(" " + p + " ")) || [, "Outro"])[1];
  const nome = (marca ? t.replace(" " + norm(marca) + " ", " ") : t).trim() || termo;
  preencherAlerta({categoria: cat, marca, nome: nome.replace(/\b\w/g, c => c.toUpperCase()), cor: ""});
  setTimeout(() => { $("#link").focus({preventScroll: true}); toast("Esse ainda não temos. Confira os campos, cole o link se tiver, e a gente vai atrás 💄"); }, 700);
}
const BUSCAS_REGISTRADAS = new Set();
function registrarCatVazia(termo) {
  const n = norm(termo);
  if (DEMO || n.length < 4 || BUSCAS_REGISTRADAS.has(n)) return;
  BUSCAS_REGISTRADAS.add(n); rpc("registrar_busca_vazia", {p_termo: termo}).catch(() => {});
}
let timerVazia;
function registrarBuscaVazia(termo) {
  clearTimeout(timerVazia);
  timerVazia = setTimeout(() => {   // só registra quando a pessoa para de digitar
    const n = norm(termo);
    if (DEMO || n.length < 4 || BUSCAS_REGISTRADAS.has(n) || norm(q.value) !== n) return;
    BUSCAS_REGISTRADAS.add(n);
    rpc("registrar_busca_vazia", {p_termo: termo}).catch(() => {});
  }, 1500);
}

function preencherAlerta({categoria, marca, nome, cor}) {
  const r = $$("#cats input").find(i => i.value === categoria) || $$("#cats input").find(i => i.value === "Outro");
  if (r) r.checked = true;
  $("#marca").value = marca || ""; $("#nome").value = nome || ""; $("#cor").value = cor || "";
  $("#alerta").scrollIntoView({behavior: "smooth"});
  setTimeout(() => ($("#email").value ? $("#btnEnviar") : $("#email")).focus({preventScroll: true}), 600);
  toast("Produto preenchido. Agora é só dizer onde te avisar 💌");
}

/* ------------------------------------------------ catálogo com filtros e páginas */
const POR_PAGINA = matchMedia("(max-width:700px)").matches ? 12 : 24;
const TIPOS = ["Blush","Batom","Gloss","Lip tint","Lápis labial","Base","Corretivo","Pó","Iluminador","Bronzer","Contorno","Sombra","Máscara de cílios","Delineador","Sobrancelha","Primer","Fixador"];
const CORES = [["Nude","#d8b49c"],["Rosa","#e68aa6"],["Vermelho","#c7202f"],["Vinho","#6d1a33"],["Marrom","#7b4a30"],["Coral e pêssego","#f28c6b"],["Roxo","#8c58b8"],["Dourado e bronze","#c9a04a"],["Prata","#c4c6cc"],["Preto","#1f1a1c"],["Branco","#ffffff"],["Transparente","#f3eeea"],["Azul e verde","#2f8f8a"]];
const TONS = ["Claro","Médio","Escuro"];
const filtrosIniciais = () => ({busca: "", marca: "", ordem: "relevancia", disp: false, tipo: "", lojas: [], cores: [], tons: [], pagina: 1});
const F = filtrosIniciais();
let catSeq = 0, VITRINE_DEMO = null;

function lerFiltrosDaUrl() {
  try { const h = new URLSearchParams(location.hash.startsWith("#catalogo?") ? location.hash.slice(10) : "");
    for (const k of ["busca", "marca", "ordem", "tipo"]) if (h.get(k)) F[k] = h.get(k);
    for (const k of ["lojas", "cores", "tons"]) if (h.get(k)) F[k] = h.get(k).split("|");
    F.disp = h.get("disp") === "1"; F.pagina = +h.get("p") || 1; } catch {}
}

function chipsCatalogo() {
  const opt = (g, v, rot, on, radio, extra = "") => `<button type="button" class="opt${radio ? " radio" : ""}${on ? " on" : ""}" data-g="${g}" data-v="${esc(v)}"><span class="cx"></span>${extra}${esc(rot)}</button>`;
  $("#fTipos").innerHTML = opt("tipo", "", "Todos os tipos", !F.tipo, true) + TIPOS.map(t => opt("tipo", t, t, F.tipo === t, true)).join("");
  $("#fLojas").innerHTML = LOJAS.map(l => l.nome).map(n => {
    const d = dominioDe(n);
    return opt("lojas", n, n, F.lojas.includes(n), false, d ? `<img src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(d)}&sz=32" alt="" data-remover>` : "");
  }).join("");
  $("#fCores").innerHTML = CORES.map(([n, hex]) => `<button type="button" class="swb${F.cores.includes(n) ? " on" : ""}" data-g="cores" data-v="${esc(n)}" title="${esc(n)}"><i style="background:${hex}"></i>${esc(n.replace(" e pêssego", "").replace(" e bronze", "").replace(" e verde", ""))}</button>`).join("");
  $("#fTons").innerHTML = TONS.map(t => opt("tons", t, "Pele " + t.toLowerCase(), F.tons.includes(t), false)).join("");
  const n = x => x ? `${x}` : "";
  $("#cTipo").textContent = F.tipo ? "1" : ""; $("#cCor").textContent = n(F.cores.length); $("#cLoja").textContent = n(F.lojas.length);
  $("#cTom").textContent = n(F.tons.length); $("#cMarca").textContent = F.marca ? "1" : "";
  $$("#catSide [data-g]").forEach(b => b.onclick = () => {
    const g = b.dataset.g, v = b.dataset.v;
    if (g === "tipo") F.tipo = v;
    else F[g] = F[g].includes(v) ? F[g].filter(x => x !== v) : [...F[g], v];
    F.pagina = 1; chipsCatalogo(); carregarCatalogo();
  });
}

function etiquetasAtivas() {
  const t = [];
  if (F.busca) t.push(["busca", "", `“${F.busca}”`]);
  if (F.disp) t.push(["disp", "", "Só disponíveis"]);
  if (F.tipo) t.push(["tipo", "", F.tipo]);
  if (F.marca) t.push(["marca", "", F.marca]);
  F.cores.forEach(c => t.push(["cores", c, c])); F.lojas.forEach(c => t.push(["lojas", c, c])); F.tons.forEach(c => t.push(["tons", c, "Pele " + c.toLowerCase()]));
  return t.map(([g, v, r]) => `<button class="tag" data-tg="${g}" data-tv="${esc(v)}">${esc(r)}<span>×</span></button>`).join("") + (t.length > 1 ? `<button class="limpar" data-limpar>Limpar tudo</button>` : "");
}
function ligarEtiquetas() {
  $$("#catInfo [data-tg]").forEach(b => b.onclick = () => {
    const g = b.dataset.tg, v = b.dataset.tv;
    if (g === "busca") { F.busca = ""; $("#fBusca").value = ""; }
    else if (g === "disp") { F.disp = false; $("#fDisp").checked = false; }
    else if (g === "tipo") F.tipo = "";
    else if (g === "marca") { F.marca = ""; $("#fMarca").value = ""; }
    else F[g] = F[g].filter(x => x !== v);
    F.pagina = 1; chipsCatalogo(); carregarCatalogo();
  });
  $("#catInfo [data-limpar]") && ($("#catInfo [data-limpar]").onclick = () => $("#fLimpar").click());
}

function filtrosAtivos() { return !!(F.busca || F.marca || F.disp || F.tipo || F.lojas.length || F.cores.length || F.tons.length); }
const arr = l => `{${l.map(x => `"${x.replace(/"/g, '\\"')}"`).join(",")}}`;

async function consultarVitrine() {
  const de = (F.pagina - 1) * POR_PAGINA;
  const ts = toks(F.busca);
  if (ts.length) {
    const l = ordenar(await pesquisarOfertas(ts, {...F}));
    return {itens: l.slice(de, de + POR_PAGINA), total: l.length};
  }
  if (DEMO) {
    await carregarDemo();
    VITRINE_DEMO ||= agregarDemo(demoCatalogo());
    let l = VITRINE_DEMO.filter(v => (!F.tipo || v.categoria === F.tipo) && (!F.disp || v.disponivel) && (!F.marca || v.marca === F.marca)
      && (!F.lojas.length || F.lojas.some(x => (F.disp ? v.lojas_disponiveis : v.lojas).includes(x)))
      && correspondeNaDemo(v, ts));
    return {itens: ordenar(l).slice(de, de + POR_PAGINA), total: l.length};
  }
  const p = new URLSearchParams({select: "grupo,marca,nome,categoria,imagem,preco_min,loja_min,url_min,lojas,lojas_disponiveis,n_lojas,n_cores,disponivel"});
  if (F.tipo) p.set("categoria", `eq.${F.tipo}`);
  if (F.marca) p.set("marca", `eq.${F.marca}`);
  if (F.disp) p.set("disponivel", "eq.true");
  if (F.lojas.length) p.set(F.disp ? "lojas_disponiveis" : "lojas", `ov.${arr(F.lojas)}`);
  if (F.cores.length) p.set("familias", `ov.${arr(F.cores)}`);
  if (F.tons.length) p.set("tons", `ov.${arr(F.tons)}`);
  if (ts.length) p.set("and", "(" + filtroDeBusca(ts) + ")");
  p.set("order", {menor: "preco_min.asc.nullslast", maior: "preco_min.desc.nullslast", lojas: "n_lojas.desc,preco_min.asc"}[F.ordem]
    || "disponivel.desc,n_lojas.desc,n_cores.desc,preco_min.asc");
  p.set("order", p.get("order") + ",grupo.asc");
  p.set("offset", de); p.set("limit", POR_PAGINA);
  const r = await fetch(`${C.supabaseUrl.replace(/\/$/, "")}/rest/v1/vitrine?${p}`, {headers: {apikey: C.supabaseAnonKey, Authorization: `Bearer ${C.supabaseAnonKey}`, Prefer: "count=exact"}});
  if (!r.ok) throw new Error(`Erro ${r.status}`);
  const total = +((r.headers.get("content-range") || "").split("/")[1] || 0);
  const itens = await r.json();
  if (!itens.length) return {itens, total};
  // Reconstrói a página com as ofertas atuais, inclusive lojas esgotadas.
  const grupos = itens.map(v => '"' + v.grupo.replace(/["\\]/g, c => "\\" + c) + '"').join(",");
  const consulta = new URLSearchParams({select: CAMPOS, grupo: "in.(" + grupos + ")", categoria: "neq.Outro", order: "id.asc", limit: 500});
  const ofertas = [];
  for (;;) {
    consulta.set("offset", ofertas.length);
    const lote = await api("catalogo?" + consulta);
    ofertas.push(...lote);
    if (lote.length < 500) break;
  }
  const atuais = new Map(agregarDemo(ofertas).map(v => [v.grupo, v]));
  return {itens: itens.filter(v => atuais.has(v.grupo)).map(v => ({...v, ...atuais.get(v.grupo), nome: v.nome, categoria: v.categoria})), total};
}
function ordenar(l) {
  const pr = v => v.preco_min ?? 1e9;
  return [...l].sort(F.ordem === "menor" ? (a, b) => pr(a) - pr(b) : F.ordem === "maior" ? (a, b) => pr(b) - pr(a)
    : F.ordem === "lojas" ? (a, b) => b.n_lojas - a.n_lojas : (a, b) => (b.disponivel - a.disponivel) || (b.n_lojas - a.n_lojas) || (b.n_cores - a.n_cores));
}
function agregarDemo(linhas) {
  const m = new Map();
  for (const r of linhas) { if (!r.categoria || r.categoria === "Outro") continue; const g = m.get(r.grupo) || []; g.push(r); m.set(r.grupo, g); }
  return [...m.entries()].map(([grupo, ls]) => {
    const disp = ls.filter(r => r.disponivel), cp = (disp.length ? disp : ls).filter(r => r.preco).sort((a, b) => a.preco - b.preco), mel = cp[0] || ls[0];
    return {grupo, fotos: fotosValidas(ls.map(r => r.imagem)), marca: ls[0].marca, nome: ls[0].produto, categoria: ls[0].categoria, imagem: (disp.find(r => r.imagem) || ls.find(r => r.imagem) || {}).imagem,
      preco_min: mel.preco, loja_min: mel.loja, url_min: mel.url_afiliado || mel.url, lojas: [...new Set(ls.map(r => r.loja))], lojas_disponiveis: [...new Set(disp.map(r => r.loja))],
      n_lojas: new Set(ls.map(r => r.loja)).size, n_cores: new Set(ls.map(r => norm(r.cor))).size, disponivel: !!disp.length, busca: ls.map(r => r.busca).join(" ")};
  });
}

function cardVitrine(v, i) {
  const outras = v.n_lojas - 1, nd = v.lojas_disponiveis?.length || 0;
  return `<article class="card" data-i="${i}" tabindex="0" role="button" aria-label="Ver lojas e preços de ${esc(v.nome)}">
    <div class="foto">${fotoOu(v.imagem, v.categoria, v.corBuscada, 120, v.fotos || [], v.fotos ? "" : v.grupo)}
      <span class="pill ${v.disponivel ? "on" : "off"}">${v.disponivel ? "Disponível" : "Esgotado"}</span></div>
    <div class="corpo">
      <div class="m">${esc(v.marca || "")}</div><div class="n">${esc(v.nome)}${v.corBuscada ? " · " + esc(v.corBuscada) : ""}</div>
      <div class="preco-linha"><b>${v.preco_min ? brl(v.preco_min) : "—"}</b><small>${v.disponivel ? "melhor preço" : "último preço"} · ${esc(v.loja_min || "")}</small></div>
      <div class="info">${(() => { const o = oficialDe(v.marca); return o && (v.lojas || []).includes(o.loja) ? '<span style="color:#5b3fa3;font-weight:600">✓ site oficial</span> · ' : ""; })()}${v.n_cores > 1 ? `${v.n_cores} cores · ` : ""}${v.n_lojas > 1 ? `${v.n_lojas} lojas` : "1 loja"}${nd && v.n_lojas > 1 ? ` · <span class="ok">tem em ${nd}</span>` : ""}</div>
    </div></article>`;
}

function paginacao(total) {
  const n = Math.max(1, Math.ceil(total / POR_PAGINA)), p = F.pagina;
  if (n <= 1) { $("#paginas").innerHTML = ""; return; }
  const nums = new Set([1, n, p - 2, p - 1, p, p + 1, p + 2].filter(x => x >= 1 && x <= n));
  let html = `<button data-p="${p - 1}" ${p === 1 ? "disabled" : ""} aria-label="Página anterior">‹</button>`, ant = 0;
  for (const x of [...nums].sort((a, b) => a - b)) { if (x - ant > 1) html += "<span>…</span>"; html += `<button data-p="${x}" class="${x === p ? "on" : ""}">${x}</button>`; ant = x; }
  html += `<button data-p="${p + 1}" ${p === n ? "disabled" : ""} aria-label="Próxima página">›</button>`;
  $("#paginas").innerHTML = html;
  $$("#paginas button[data-p]").forEach(b => b.onclick = () => { F.pagina = +b.dataset.p; carregarCatalogo(); $("#catalogo").scrollIntoView({behavior: "smooth"}); });
}

let ITENS_CAT = [];
async function carregarCatalogo() {
  const meu = ++catSeq;
  $("#fLimpar").style.visibility = filtrosAtivos() ? "visible" : "hidden";
  try { history.replaceState(null, "", filtrosAtivos() || F.pagina > 1 ? "#catalogo?" + new URLSearchParams(Object.entries({busca: F.busca, marca: F.marca, ordem: F.ordem === "relevancia" ? "" : F.ordem, tipo: F.tipo, lojas: F.lojas.join("|"), cores: F.cores.join("|"), tons: F.tons.join("|"), disp: F.disp ? "1" : "", p: F.pagina > 1 ? F.pagina : ""}).filter(([, v]) => v)) : location.pathname); } catch {}
  $("#gradeCat").style.opacity = .5;
  try {
    const {itens, total} = await consultarVitrine();
    if (meu !== catSeq) return;
    ITENS_CAT = itens;
    $("#catInfo").innerHTML = `<span>${total ? `<b>${total.toLocaleString("pt-BR")}</b> produto${total > 1 ? "s" : ""}` : "Nenhum produto"}</span>` + etiquetasAtivas();
    ligarEtiquetas();
    $("#sideVer").textContent = total ? `Ver ${total.toLocaleString("pt-BR")} produtos` : "Ver produtos";
    $("#gradeCat").innerHTML = itens.map(cardVitrine).join("") || (F.busca && !(F.marca || F.disp || F.tipo || F.lojas.length || F.cores.length || F.tons.length) ? (registrarCatVazia(F.busca), `<div class="vazio"><b>“${esc(F.busca)}” ainda não está na nossa plataforma.</b><br>Peça pra gente que a gente vai atrás e te avisa quando achar (se tiver o link, mande junto).<br><br><a href="#alerta" id="pedirBuscaAtual" style="color:var(--rosa);font-weight:700">Pedir este produto →</a> · <button class="limpar" data-limpar-vazio>Limpar filtros</button></div>`) : `<div class="vazio">Nada encontrado com esses filtros. <button class="limpar" data-limpar-vazio>Limpar filtros</button> ou <a href="#alerta" style="color:var(--rosa);font-weight:600">crie um alerta</a> que a gente procura pra você.</div>`);
    const limpar = $("#gradeCat [data-limpar-vazio]");
    if (limpar) limpar.onclick = () => $("#fLimpar").click();
    const pedir = $("#pedirBuscaAtual");
    if (pedir) pedir.onclick = e => { e.preventDefault(); pedirProduto(F.busca); };
    $$("#gradeCat .card").forEach(c => { const abre = () => abrirProduto(ITENS_CAT[+c.dataset.i]); c.onclick = abre; c.onkeydown = e => { if (e.key === "Enter") abre(); }; });
    paginacao(total);
  } catch (e) {
    if (meu !== catSeq) return;
    console.warn(e);
    $("#gradeCat").innerHTML = `<div class="vazio">O catálogo está sendo atualizado. Volte em alguns minutos. 💄</div>`; $("#paginas").innerHTML = ""; $("#catInfo").innerHTML = "";
  } finally { if (meu === catSeq) $("#gradeCat").style.opacity = 1; }
}

async function iniciarCatalogo() {
  lerFiltrosDaUrl();
  await carregarOficiais();
  $("#fBusca").value = F.busca; $("#fOrdem").value = F.ordem; $("#fDisp").checked = F.disp;
  try {
    const marcas = DEMO ? [...new Set(demoCatalogo().map(r => r.marca).filter(Boolean))].sort().map(m => ({marca: m})) : await rpc("marcas_vitrine", {});
    $("#fMarca").innerHTML = `<option value="">Todas as marcas</option>` + marcas.map(m => `<option value="${esc(m.marca)}"${m.marca === F.marca ? " selected" : ""}>${esc(m.marca)}${m.total ? ` (${m.total})` : ""}</option>`).join("");
  } catch (e) { console.warn(e); }
  chipsCatalogo();
  const side = $("#catSide"), fundo = $("#catFundo"), fechar = () => { side.classList.remove("on"); fundo.classList.remove("on"); destravarFundo(); };
  $("#abrirFiltros").onclick = () => { side.classList.add("on"); fundo.classList.add("on"); travarFundo(); };
  fundo.onclick = fechar;
  addEventListener("keydown", e => { if (e.key === "Escape" && side.classList.contains("on")) fechar(); });
  // arrastar a gaveta pra esquerda também fecha
  let x0 = null;
  side.addEventListener("touchstart", e => { x0 = e.touches[0].clientX; }, {passive: true});
  side.addEventListener("touchend", e => { if (x0 !== null && e.changedTouches[0].clientX - x0 < -60) fechar(); x0 = null; }, {passive: true});
  $("#sideFechar").onclick = fechar; $("#sideVer").onclick = () => { fechar(); $("#catalogo").scrollIntoView({behavior: "smooth"}); };
  let t;
  $("#fBusca").oninput = e => { clearTimeout(t); t = setTimeout(() => { F.busca = e.target.value.trim(); F.pagina = 1; carregarCatalogo(); }, 300); };
  $("#fMarca").onchange = e => { F.marca = e.target.value; F.pagina = 1; carregarCatalogo(); };
  $("#fOrdem").onchange = e => { F.ordem = e.target.value; F.pagina = 1; carregarCatalogo(); };
  $("#fDisp").onchange = e => { F.disp = e.target.checked; F.pagina = 1; carregarCatalogo(); };
  $("#fLimpar").onclick = () => { Object.assign(F, {busca: "", marca: "", ordem: "relevancia", disp: false, tipo: "", lojas: [], cores: [], tons: [], pagina: 1});
    $("#fBusca").value = ""; $("#fMarca").value = ""; $("#fOrdem").value = "relevancia"; $("#fDisp").checked = false; chipsCatalogo(); carregarCatalogo(); };
  await carregarCatalogo();
  if (location.hash.startsWith("#catalogo?")) $("#catalogo").scrollIntoView();
}

/* ------------------------------------------------ radar (vitrine) */
let filtro = "Todos";
function renderRadar() {
  const cats = ["Todos", ...new Set(RADAR.map(p => p.categoria))];
  $("#filtros").innerHTML = cats.map(c => `<button class="filtro${c === filtro ? " on" : ""}" data-c="${esc(c)}">${esc(c)}${c === "Todos" ? ` (${RADAR.length})` : ""}</button>`).join("");
  $$(".filtro").forEach(b => b.onclick = () => { filtro = b.dataset.c; renderRadar(); });
  const lista = RADAR.filter(p => filtro === "Todos" || p.categoria === filtro)
    .sort((a, b) => (b.disponivel - a.disponivel) || (new Date(b.criado_em) - new Date(a.criado_em)));
  $("#grade").innerHTML = lista.map(p => {
    const ofs = (p.ofertas || []).slice().sort((a, b) => (b.disponivel - a.disponivel) || ((a.preco || 1e9) - (b.preco || 1e9)));
    const porLoja = []; const vistos = new Set();
    for (const o of ofs) if (!vistos.has(o.loja)) { vistos.add(o.loja); porLoja.push(o); }
    const img = ofs.find(o => o.imagem)?.imagem || p.imagem_loja || p.foto_url;
    const melhor = porLoja.find(o => o.disponivel);
    return `<article class="card">
      <div class="foto">${fotoOu(img, p.categoria, corDe(p.cor || p.nome), 150)}
        <span class="pill ${p.disponivel ? "on" : "off"}">${p.exemplo ? (p.disponivel ? "Disponível" : "Esgotado") : (p.disponivel ? "Voltou!" : "Esgotado")}</span><span class="cat">${esc(p.categoria)}</span></div>
      <div class="corpo">
        <div class="m">${esc(p.marca)}</div><div class="n">${esc(p.nome)}</div>${p.cor ? `<div class="c">${esc(p.cor)}</div>` : ""}
        <div class="mini-lojas">${porLoja.slice(0, 4).map(o => `<div class="ml${o.disponivel ? " on" : ""}"><span class="pt"></span>${esc(o.loja)}<span class="pr">${o.disponivel ? `<a href="${esc(urlSegura(o.url_afiliado || o.url))}" target="_blank" rel="noopener sponsored">${o.preco ? brl(o.preco) : "Comprar"} →</a>` : (o.preco ? `<span style="color:var(--suave);font-weight:500">${brl(o.preco)}</span>` : "")}</span></div>`).join("") || `<div class="ml"><span class="pt"></span>Procurando nas lojas…</div>`}</div>
        <div class="rodape">
          ${melhor ? `<a class="btn btn-esc" href="${esc(urlSegura(melhor.url_afiliado || melhor.url))}" target="_blank" rel="noopener sponsored">Comprar</a>` : ""}
          <button class="btn btn-linha" data-avisar='${esc(JSON.stringify({categoria: p.categoria, marca: p.marca, nome: p.nome, cor: p.cor || ""}))}'>Me avisa também</button>
        </div>
      </div></article>`;
  }).join("") || `<div class="vazio">Nenhum produto no radar ainda. Seja a primeira a criar um alerta! 💄</div>`;
  $$("[data-avisar]").forEach(b => b.onclick = () => preencherAlerta(JSON.parse(b.dataset.avisar)));

  // vitrine do topo + ticker
  const destaque = [...RADAR].sort((a, b) => b.disponivel - a.disponivel).slice(0, 3);
  $("#vitrineHero").innerHTML = destaque.map(p => {
    const img = (p.ofertas || []).find(o => o.imagem)?.imagem || p.imagem_loja || p.foto_url;
    return `<div class="flutua"><div class="foto">${fotoOu(img, p.categoria, corDe(p.cor || p.nome), 150)}</div><span class="pill ${p.disponivel ? "on" : "off"}">${p.disponivel ? (p.exemplo ? "Disponível" : "Voltou!") : "Esgotado"}</span><div class="m">${esc(p.marca)}</div><div class="n">${esc(p.nome)}</div></div>`;
  }).join("");
  const voltaram = RADAR.filter(p => p.disponivel && !p.exemplo && !DEMO);
  if (voltaram.length) {
    const itens = voltaram.map(p => { const o = (p.ofertas || []).find(o => o.disponivel);
      return `<span><i>● VOLTOU</i> &nbsp;<b>${esc(p.marca)} ${esc(p.nome)}${p.cor ? " · " + esc(p.cor) : ""}</b>${o ? " na " + esc(o.loja) : ""} ${tempo(p.disponivel_desde)}</span>`; }).join("");
    $("#faixa").innerHTML = itens + itens; $("#ticker").hidden = false;
  }
}

function renderLojas() {
  $("#lojasGrade").innerHTML = LOJAS.map(l => `<div class="loja-chip">${logoLoja(l.nome)}<div><b>${esc(l.nome)}</b><span>${esc(l.frequencia || "Fonte cadastrada")}</span></div><span class="ok${l.ok === true ? " on" : ""}" title="${l.ok === false ? "com problema na última checagem" : l.ok === true ? "funcionando" : "aguardando confirmação"}"></span></div>`).join("");
}

/* ------------------------------------------------ formulário */
$("#cats").innerHTML = CATEGORIAS.map((c, i) => `<label><input type="radio" name="cat" value="${esc(c)}"${i === 0 ? " checked" : ""}><span>${esc(c)}</span></label>`).join("");
$("#marcas").innerHTML = MARCAS.map(m => `<option value="${esc(m)}">`).join("");

$("#querWpp").onchange = e => $("#wppBox").classList.toggle("on", e.target.checked);
$("#whatsapp").oninput = e => { let d = e.target.value.replace(/\D/g, "").slice(0, 13); if (d.startsWith("55") && d.length > 11) d = d.slice(2);
  e.target.value = d.length > 6 ? `(${d.slice(0,2)}) ${d.slice(2, d.length - 4)}-${d.slice(-4)}` : d.length > 2 ? `(${d.slice(0,2)}) ${d.slice(2)}` : d; };

let fotoBlob = null;
async function comprimir(arquivo) {
  const bmp = await createImageBitmap(arquivo);
  const k = Math.min(1, 1000 / Math.max(bmp.width, bmp.height));
  const cv = Object.assign(document.createElement("canvas"), {width: Math.round(bmp.width * k), height: Math.round(bmp.height * k)});
  cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
  bmp.close();
  return new Promise(ok => cv.toBlob(ok, "image/webp", .85));
}
async function usarFoto(arq) {
  if (!arq) return;
  if (!["image/png", "image/jpeg", "image/webp"].includes(arq.type) || arq.size > 5 * 1024 * 1024) {
    return toast("Escolha uma foto JPG, PNG ou WebP de até 5 MB.");
  }
  try {
    const blob = await comprimir(arq);
    if (!blob) throw new Error("imagem inválida");
    fotoBlob = blob;
    const img = new Image();
    const preview = URL.createObjectURL(blob);
    img.alt = "Prévia da foto";
    img.onload = img.onerror = () => URL.revokeObjectURL(preview);
    img.src = preview;
    $("#fotoPrev").replaceChildren(img);
  } catch { toast("Não foi possível ler essa foto."); }
}
$("#foto").onchange = e => usarFoto(e.target.files[0]);
const drop = $("#fotoDrop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("arrastando"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("arrastando"); }));
drop.addEventListener("drop", e => usarFoto(e.dataTransfer.files[0]));

async function enviarFoto() {
  if (!fotoBlob || DEMO) return null;
  const tipo = fotoBlob.type || "image/webp", ext = tipo.split("/")[1] || "webp";
  const nome = `${new Date().toISOString().slice(0, 10)}/${crypto.randomUUID()}.${ext}`;
  const base = C.supabaseUrl.replace(/\/$/, "");
  const r = await fetch(`${base}/storage/v1/object/fotos/${nome}`, {method: "POST",
    headers: {apikey: C.supabaseAnonKey, Authorization: `Bearer ${C.supabaseAnonKey}`, "Content-Type": tipo}, body: fotoBlob});
  if (!r.ok) { console.warn("foto", await r.text()); return null; }
  return `${base}/storage/v1/object/public/fotos/${nome}`;
}

function mostrarErro(msg) { const e = $("#erro"); e.textContent = msg; e.classList.toggle("on", !!msg); if (msg) e.scrollIntoView({behavior: "smooth", block: "center"}); }

$("#form").onsubmit = async e => {
  e.preventDefault(); mostrarErro("");
  const v = id => $("#" + id).value.trim();
  const querWpp = $("#querWpp").checked, wpp = v("whatsapp").replace(/\D/g, "");
  if (!v("marca") || !v("nome")) return mostrarErro("Conta pra gente a marca e o nome do produto.");
  if (!v("email") && !(querWpp && wpp)) return mostrarErro("Coloque um e-mail ou um WhatsApp para receber o aviso.");
  if (v("email") && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v("email"))) return mostrarErro("Esse e-mail parece incompleto.");
  if (querWpp && wpp && wpp.length < 10) return mostrarErro("Coloque o WhatsApp com DDD.");
  if (querWpp && wpp && !v("chave") && !v("email")) return mostrarErro("Informe o código do CallMeBot para usar o WhatsApp, ou cadastre um e-mail.");
  if (v("link") && !/^https?:\/\//i.test(v("link"))) return mostrarErro("O link precisa começar com https://");
  if (!$("#aceite").checked) return mostrarErro("Marque a caixinha de aceite para continuarmos.");

  const btn = $("#btnEnviar"); btn.disabled = true; btn.innerHTML = '<span class="carregando"></span> Criando alerta…';
  try {
    const dados = {p_categoria: $("input[name=cat]:checked")?.value || "Outro", p_marca: v("marca"), p_nome: v("nome"), p_cor: v("cor"),
      p_link: v("link"), p_pessoa: v("pessoa"), p_email: v("email"), p_whatsapp: querWpp ? wpp : "", p_callmebot: querWpp ? v("chave") : ""};
    let res;
    if (DEMO) { await new Promise(r => setTimeout(r, 700)); res = {token: "demo"}; }
    else { dados.p_foto_url = await enviarFoto(); res = await rpc("criar_alerta", dados); }
    const nomeP = [dados.p_marca, dados.p_nome, dados.p_cor].filter(Boolean).join(" · ");
    $("#formCorpo").hidden = true;
    $("#formOk").hidden = false;
    $("#formOk").innerHTML = `<div class="sucesso"><div class="ok">✓</div><h3>Alerta criado!</h3>
      <p>Estamos de olho em <b>${esc(nomeP)}</b>.<br>Assim que voltar, você recebe ${[dados.p_email && "um e-mail", dados.p_whatsapp && dados.p_callmebot && "uma mensagem no WhatsApp"].filter(Boolean).join(" e ") || "o aviso"} com o link da loja.</p>
      ${dados.p_whatsapp && !dados.p_callmebot ? `<p style="font-size:13px;color:#9b2c45">Lembrete: sem o código do WhatsApp, o aviso vai só por e-mail.</p>` : ""}
      <button class="btn btn-linha" id="novoAlerta" type="button" style="margin-top:10px">Criar outro alerta</button></div>`;
    $("#novoAlerta").onclick = () => { $("#formOk").hidden = true; $("#formCorpo").hidden = false; ["nome", "cor", "link"].forEach(i => $("#" + i).value = ""); fotoBlob = null; $("#fotoPrev").innerHTML = "📷"; };
    if (!DEMO) carregarRadar();
  } catch (err) {
    mostrarErro(err.message || "Não deu certo agora. Tenta de novo em instantes?");
  } finally { btn.disabled = false; btn.textContent = "Criar meu alerta"; }
};

/* ------------------------------------------------ cancelar alerta (?cancelar=token) */
function modal(html) { $("#modalCaixa").innerHTML = html; $("#modal").classList.add("on"); }
$("#modal").onclick = e => { if (e.target.id === "modal") $("#modal").classList.remove("on"); };
function talvezCancelar() {
  const token = new URLSearchParams(location.search).get("cancelar");
  if (!token) return;
  modal(`<h3>Parar este alerta?</h3><p>Você não vai mais receber avisos deste produto.</p>
    <div style="display:flex;gap:10px;justify-content:center;margin-top:18px"><button class="btn btn-linha" id="mNao">Manter</button><button class="btn btn-esc" id="mSim">Parar alerta</button></div>`);
  $("#mNao").onclick = () => { $("#modal").classList.remove("on"); history.replaceState(null, "", location.pathname); };
  $("#mSim").onclick = async () => {
    try { const ok = DEMO ? true : await rpc("cancelar_alerta", {p_token: token});
      modal(`<h3>${ok ? "Pronto!" : "Hmm…"}</h3><p>${ok ? "Alerta cancelado. Quando quiser, é só criar outro. 💕" : "Não achamos esse alerta. Talvez ele já tenha sido cancelado."}</p><button class="btn btn-esc" id="mFechar">Fechar</button>`);
      $("#mFechar").onclick = () => $("#modal").classList.remove("on");
      history.replaceState(null, "", location.pathname);
    } catch (e) { toast("Não consegui cancelar agora. Tenta de novo?"); }
  };
}

/* ------------------------------------------------ util */
let tt; function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("on"), 3200); }
addEventListener("scroll", () => $("#topo").classList.toggle("rolou", scrollY > 10), {passive: true});
function exemplos(nomes) {
  nomes = nomes.filter(t => t && t.length >= 4 && !/^[\d\s.,]+$/.test(t) && !/^cor\s/i.test(t));
  [...new Set(nomes.filter(Boolean))].slice(0, 5).forEach(t => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = t;
    b.onclick = () => { q.value = t; buscarNoCatalogo(); }; $("#exemplos").appendChild(b);
  });
}
const anima = (el, n) => { n = +n || 0; let i = 0; const passos = 24; const f = () => { i++; el.textContent = Math.round(n * i / passos).toLocaleString("pt-BR"); if (i < passos) requestAnimationFrame(f); }; f(); };

/* ------------------------------------------------ carregar */
async function vitrineDoCatalogo() {
  // enquanto ninguém criou alerta, mostra produtos reais do catálogo
  const linhas = await api("catalogo?select=loja,marca,produto,cor,categoria,titulo,url,url_afiliado,imagem,preco,disponivel,grupo,atualizado_em&imagem=not.is.null&preco=not.is.null&categoria=neq.Outro&order=atualizado_em.desc&limit=600");
  DEMO_DADOS = {catalogo: linhas.sort(() => Math.random() - .5)};
  return demoRadar();
}
async function carregarRadar() {
  RADAR = DEMO ? demoRadar() : await api("produtos?select=id,categoria,marca,nome,cor,foto_url,imagem_loja,disponivel,disponivel_desde,criado_em,ultima_verificacao,ofertas(loja,preco,disponivel,url,url_afiliado,imagem,atualizado_em)&order=criado_em.desc&limit=120");
  if (!DEMO && !RADAR.length) { try { RADAR = await vitrineDoCatalogo(); RADAR.forEach(p => p.exemplo = true);
      $("#radar h2").innerHTML = "Direto das lojas, <em>agora</em>";
      $("#radar .titulo-sec p").textContent = "Uma amostra do nosso catálogo, com estoque e preço reais. Assim que alguém criar um alerta, ele aparece aqui."; } catch (e) { console.warn(e); } }
  renderRadar();
}
async function iniciar() {
  if (DEMO) $("#demoBar").hidden = false;
  if (C.contato) $("#rodapeTxt").textContent += " Contato: " + C.contato;
  talvezCancelar();
  try {
    if (DEMO) {
      const d = await carregarDemo();
      if (d.gerado_em) $("#demoBar").innerHTML = `<b>Prévia:</b> produtos, fotos, preços e estoque reais das lojas, capturados ${esc(tempo(d.gerado_em))}. Alertas ainda não são salvos.`;
    }
    const [fontes, atividade] = await Promise.all([
      fetch("lojas.json").then(r => r.json()).catch(() => []),
      DEMO ? (DEMO_DADOS.lojas || []) : api("lojas?select=*&order=nome").catch(() => [])
    ]);
    const diretorio = new Map(fontes.map(l => [l.nome, l]));
    for (const l of atividade) diretorio.set(l.nome, {...diretorio.get(l.nome), ...l});
    LOJAS = [...diretorio.values()].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
    renderLojas();
    iniciarCatalogo();
    await carregarRadar();
    exemplos(["Blush", "Batom vermelho", "Base", "Gloss", "MAC", ...RADAR.map(p => p.marca)].filter((v, i, a) => a.indexOf(v) === i));
    const est = DEMO ? {produtos: RADAR.length, lojas: LOJAS.length, catalogo: demoCatalogo().length} : await rpc("estatisticas", {});
    if (!est.produtos) $("#nProdutos").parentElement.remove(); else anima($("#nProdutos"), est.produtos); anima($("#nLojas"), est.lojas || LOJAS.length); anima($("#nCatalogo"), est.catalogo);
  } catch (e) {
    console.error(e);
    $("#grade").innerHTML = `<div class="vazio">Não consegui carregar agora (${esc(e.message)}). Confira o <code>config.js</code> e se o SQL foi executado no Supabase.</div>`;
  }
}
if (matchMedia("(max-width:700px)").matches) { $("#q").placeholder = "Buscar make ou marca"; $("#fBusca").placeholder = "Buscar no catálogo"; }
try {   // menu de baixo: some ao rolar pra baixo, volta ao rolar pra cima
  const nb = $(".nav-baixo"); let ultimoY = scrollY, tic = false;
  addEventListener("scroll", () => {
    if (tic) return; tic = true;
    requestAnimationFrame(() => {
      const y = scrollY, d = y - ultimoY;
      if (Math.abs(d) > 6) { nb.classList.toggle("escondida", d > 0 && y > 120); ultimoY = y; }
      if (innerHeight + y >= document.body.scrollHeight - 40) nb.classList.remove("escondida");
      tic = false;
    });
  }, {passive: true});
} catch {}
try {
  const links = $$(".nav-baixo a"), secs = links.map(a => document.getElementById(a.dataset.s)).filter(Boolean);
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) links.forEach(a => a.classList.toggle("on", a.dataset.s === e.target.id)); }), {rootMargin: "-45% 0px -50% 0px"});
  secs.forEach(x => io.observe(x));
} catch {}
iniciar();
})();
