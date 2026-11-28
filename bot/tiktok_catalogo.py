"""
Catálogo do TikTok Shop (2x por dia): percorre as categorias de maquiagem do
TikTok Shop Brasil e guarda os produtos de TODAS as lojas/vendedores que
aparecem lá (marca, produto, preço, foto e se está esgotado).

O site web do TikTok Shop não tem busca e não tem API aberta, então o bot abre
as páginas de categoria num navegador de verdade (Playwright/Chromium), clica
em "Ver mais" até acabar e lê os cards. Cada categoria mostra no máximo ~100
produtos por vez, então o catálogo do TikTok nunca é 100% completo.

Configuração em config/lojas.yaml -> tiktok_catalogo.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import time
from urllib.parse import urlsplit

from .catalogo import MARCAS, categoria_de, linha_catalogo
from .util import Oferta, normalizar, preco_float

log = logging.getLogger("tiktok")

LOJA = "TikTok Shop"
BASE = "https://shop.tiktok.com/br/c/"

# categoria do TikTok -> categoria do site (None = descobre pelo nome do produto)
CATEGORIAS_PADRAO = {
    "lipstick-lip-gloss/601534": "Batom",
    "eyeliner-lipliner/601587": "Delineador",
    "eyebrow-products/601586": "Sobrancelha",
    "eyeshadow/601588": "Sombra",
    "concealer-foundation/601554": "Base",
    "mascara/601585": "Máscara de cílios",
    "powder/601558": "Pó",
    "blush/601560": "Blush",
    "bb-cc-creams/601550": "Base",
    "bronzer-highlighter/601555": "Iluminador",
    "makeup-base-and-primers/601556": "Primer",
    "makeup-fixing-spray/601552": "Fixador",
    "makeup-sets/601529": None,
    "makeup/848648": None,
}

# marcas que aparecem muito no TikTok Shop, além das do catálogo geral
MARCAS_TIKTOK = [
    "Sarah's Beauty", "Sarahs Beauty", "Yvisy", "Playboy", "Max Love", "Macrilan", "Belle Angel", "Ludurana",
    "Fenzza", "Pink 21", "Miss Rôse", "Miss Rose", "Febella", "Luisance", "Jasmyne", "Mia Make", "Dapop",
    "Ruby Kisses", "Phállebeauty", "Phallebeauty", "City Girls", "Vivai", "Super Poderes", "Simple Organic",
    "Nina Makeup", "Klasme", "Hello Mini", "Lua & Neve", "Boca Rosa Beauty", "Wepink", "Sallve", "Creamy",
    "Sheglam", "Kiko Milano", "Essence", "Catrice", "Romand", "Glow Recipe", "Bt Beauty", "Bruna Tavares",
    "Bauny", "Lady Beauty", "Tracta", "Vizzela", "Koloss", "Zanphy", "Mahav", "Fand Makeup", "Bitarra",
    "Lanell", "Sunnys", "NewShow", "Kiss New York", "Revolution", "Makeup Revolution", "Tarte", "Sol de Janeiro",
]

PRECO_RE = re.compile(r"R\$\s*([\d.]+,\d{2})")
ID_RE = re.compile(r"/pdp/[^/?#]+/(\d+)")
PALAVRAS_ESGOTADO = ("esgotado", "sem estoque", "indisponível", "indisponivel", "fora de estoque")
PALAVRAS_COMPRA = ("comprar agora", "adicionar ao carrinho")


class Bloqueado(Exception):
    """O TikTok mostrou a verificação de segurança (CAPTCHA)."""


# No modo Chrome (no seu PC), quando aparece a verificação o robô espera você
# resolver na janela em vez de desistir. 0 = desiste na hora (GitHub).
ESPERA_CAPTCHA_SEG = 0


# ---------------------------------------------------------------------------
# Partes "puras" (sem navegador) — testadas em tests/test_bot.py
# ---------------------------------------------------------------------------
def _lista_marcas(extra: list[str] | None = None) -> list[tuple[str, str]]:
    """[(nome bonito, nome normalizado)] da maior para a menor (pega "Boca Rosa Beauty" antes de "Boca Rosa")."""
    vistos: dict[str, str] = {}
    for m in list(MARCAS) + MARCAS_TIKTOK + list(extra or []):
        n = normalizar(m)
        if n and n not in vistos:
            vistos[n] = m
    vistos.setdefault("m a c", "MAC")  # "M·A·C" vira "m a c"
    return sorted(((v, k) for k, v in vistos.items()), key=lambda x: -len(x[1]))


def marca_do_titulo(titulo: str, marcas: list[tuple[str, str]]) -> str | None:
    t = f" {normalizar(titulo)} "
    for bonito, n in marcas:
        if f" {n} " in t:
            return "MAC" if n in ("mac", "m a c", "mac cosmetics") else bonito
    return None


def card_para_oferta(card: dict, marcas: list[tuple[str, str]]) -> Oferta | None:
    """card = {link, titulo, texto, imagem} lido da página de categoria."""
    titulo = (card.get("titulo") or "").split("\n")[0].strip()
    link = (card.get("link") or "").split("?")[0]
    m = ID_RE.search(link)
    if not titulo or not m:
        return None
    texto = card.get("texto") or ""
    precos = PRECO_RE.findall(texto)
    baixo = texto.lower()
    disponivel = not any(p in baixo for p in PALAVRAS_ESGOTADO)
    marca = marca_do_titulo(titulo, marcas)
    return Oferta(LOJA, titulo, link, disponivel, card.get("imagem") or None,
                  preco_float(precos[0]) if precos else None,
                  extra={"marca": marca or "", "produto": titulo, "cor": None, "categorias": "",
                         "tiktok_id": m.group(1),
                         "preco_de": preco_float(precos[1]) if len(precos) > 1 else None})


def ler_pagina_produto(texto: str) -> dict:
    """Do texto da página do produto: marca, vendedor e se dá pra comprar."""
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    marca = vendedor = None
    for i, l in enumerate(linhas):
        b = l.lower()
        if vendedor is None and b.startswith("vendido por"):
            vendedor = l[len("vendido por"):].strip() or None
        if marca is None and (b == "marca" or b.startswith("marca ")):
            marca = l[5:].strip() or (linhas[i + 1] if i + 1 < len(linhas) else None)
    baixo = texto.lower()
    corte = baixo.find("sobre este produto")
    area = baixo[:corte] if corte > 0 else baixo[:4000]  # ignora avaliações
    if any(p in area for p in PALAVRAS_ESGOTADO):
        disp = False
    elif any(p in area for p in PALAVRAS_COMPRA):
        disp = True
    else:
        disp = None
    return {"marca": marca, "vendedor": vendedor, "disponivel": disp}


def montar_linhas(ofertas: list[tuple[Oferta, str | None]], agora: dt.datetime) -> list[dict]:
    """Oferta + categoria do TikTok -> linhas da tabela catalogo (só maquiagem)."""
    linhas: dict[str, dict] = {}
    for o, cat_tiktok in ofertas:
        cat = categoria_de(o, cat_tiktok)
        if cat == "Outro":
            continue
        l = linha_catalogo(o, cat, agora, "")
        linhas.setdefault(l["url"], l)
    return list(linhas.values())


# ---------------------------------------------------------------------------
# Navegador
# ---------------------------------------------------------------------------
_JS_CARDS = """() => [...document.querySelectorAll('a[href*="/pdp/"]')].map(a => {
    let c = a;
    for (let i = 0; i < 6 && c.parentElement; i++) {
        c = c.parentElement;
        if (/R\\$/.test(c.innerText)) break;
    }
    const img = a.querySelector('img') || c.querySelector('img');
    return {link: a.href, titulo: a.innerText.trim(), texto: c.innerText, imagem: img ? (img.currentSrc || img.src) : null};
})"""


def _tem_verificacao(page) -> bool:
    try:
        if "security check" in (page.title() or "").lower():
            return True
        corpo = page.inner_text("body", timeout=3000)[:2000].lower()
    except Exception:  # noqa: BLE001
        return False
    return "verify to continue" in corpo or "drag the puzzle" in corpo


def _checar_bloqueio(page):
    if not _tem_verificacao(page):
        return
    if ESPERA_CAPTCHA_SEG <= 0:
        raise Bloqueado(page.url)
    log.warning("O TikTok pediu verificação. Resolva o quebra-cabeça na janela do Chrome "
                "(espero até %d min)...", ESPERA_CAPTCHA_SEG // 60)
    try:
        page.bring_to_front()
    except Exception:  # noqa: BLE001
        pass
    fim = time.time() + ESPERA_CAPTCHA_SEG
    while time.time() < fim:
        time.sleep(4)
        if not _tem_verificacao(page):
            log.info("Verificação resolvida, continuando.")
            time.sleep(2)
            return
    raise Bloqueado(page.url)


def _abrir(page, url):
    resposta = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if resposta and resposta.status in (401, 403, 429):
        raise Bloqueado(f"HTTP {resposta.status}")
    if resposta and resposta.status >= 400:
        raise RuntimeError(f"HTTP {resposta.status}")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(1.5)
    destino = urlsplit(page.url)
    log.info("TikTok: HTTP %s, destino %s%s, título %r", resposta.status if resposta else "?",
             destino.hostname, destino.path[:180], page.title()[:120])
    _checar_bloqueio(page)
    if destino.path.startswith(("/us/", "/gb/", "/uk/")):
        raise Bloqueado("TikTok redirecionou a coleta BR para " + destino.path.split("/")[1])


def _cards_da_categoria(page, url, cliques: int, espera: float) -> list[dict]:
    _abrir(page, url)
    ultimo = 0
    for _ in range(cliques):
        botao = page.get_by_role("button", name="Ver mais", exact=True)
        if botao.count() == 0:
            break
        try:
            botao.first.scroll_into_view_if_needed(timeout=5000)
            botao.first.click(timeout=5000)
        except Exception:  # noqa: BLE001
            break
        time.sleep(espera)
        _checar_bloqueio(page)
        n = page.locator('a[href*="/pdp/"]').count()
        if n == ultimo:
            break
        ultimo = n
    cards = page.evaluate(_JS_CARDS)
    if not cards:
        log.warning("Categoria sem cards: %d links na página, %d apontam para /pdp/",
                    page.locator("a[href]").count(), page.locator('a[href*="/pdp/"]').count())
    return cards


def _abrir_navegador(pw, chrome: bool):
    """chrome=True: abre o Google Chrome instalado no PC, com janela, num perfil só do robô
    (fica salvo, então a verificação do TikTok aparece bem menos). False: Chromium invisível (GitHub)."""
    if chrome:
        import os
        perfil = os.path.join(os.path.expanduser("~"), ".voltou-robo-chrome")
        ctx = pw.chromium.launch_persistent_context(
            perfil, channel="chrome", headless=False, locale="pt-BR", timezone_id="America/Sao_Paulo",
            viewport=None, args=["--start-maximized"])
        return ctx, ctx
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="pt-BR", timezone_id="America/Sao_Paulo", viewport={"width": 1440, "height": 900})
    return browser, ctx


def coletar(cfg: dict, agora: dt.datetime | None = None, chrome: bool = False) -> tuple[list[dict], bool]:
    """Devolve (linhas do catálogo, completo?). completo=False se o TikTok bloqueou no meio."""
    global ESPERA_CAPTCHA_SEG
    from playwright.sync_api import sync_playwright  # só o workflow do TikTok instala

    agora = agora or dt.datetime.now(dt.timezone.utc)
    conf = cfg.get("tiktok_catalogo") or {}
    categorias = conf.get("categorias") or CATEGORIAS_PADRAO
    cliques = int(conf.get("max_cliques_ver_mais", 15))
    espera = float(conf.get("espera_entre_cliques_seg", 2.0))
    detalhar = int(conf.get("detalhar_max", 40))
    marcas = _lista_marcas(conf.get("marcas_extra"))
    ESPERA_CAPTCHA_SEG = int(conf.get("esperar_verificacao_min", 10)) * 60 if chrome else 0

    ofertas: dict[str, tuple[Oferta, str | None]] = {}
    completo = True
    with sync_playwright() as pw:
        browser, ctx = _abrir_navegador(pw, chrome)
        page = ctx.pages[0] if chrome and ctx.pages else ctx.new_page()
        try:
            for slug, cat in categorias.items():
                try:
                    cards = _cards_da_categoria(page, BASE + slug, cliques, espera)
                except Bloqueado:
                    raise
                except Exception as e:  # noqa: BLE001
                    log.warning("TikTok %s: %s", slug, e)
                    completo = False
                    continue
                if not cards:
                    completo = False
                novos = 0
                for c in cards:
                    o = card_para_oferta(c, marcas)
                    if o and o.extra["tiktok_id"] not in ofertas:
                        ofertas[o.extra["tiktok_id"]] = (o, cat)
                        novos += 1
                log.info("TikTok %s: %d cards, %d novos", slug, len(cards), novos)

            # abre alguns produtos sem marca reconhecida pra descobrir a marca (e conferir estoque)
            sem_marca = [o for o, _ in ofertas.values() if not o.extra.get("marca")][:detalhar]
            for o in sem_marca:
                try:
                    _abrir(page, o.url)
                    info = ler_pagina_produto(page.inner_text("body"))
                except Bloqueado:
                    raise
                except Exception as e:  # noqa: BLE001
                    log.info("TikTok produto %s: %s", o.url, e)
                    continue
                if info["marca"] and normalizar(info["marca"]) not in ("sem marca", "generico", "generica", "outros"):
                    o.extra["marca"] = info["marca"]
                if info["disponivel"] is not None:
                    o.disponivel = info["disponivel"]
                time.sleep(1)
        except Bloqueado as b:
            completo = False
            log.warning("TikTok pediu verificação (CAPTCHA) em %s — salvando o que deu pra pegar", b)
        finally:
            browser.close()

    linhas = montar_linhas(list(ofertas.values()), agora)
    log.info("TikTok: %d produtos de maquiagem (%d marcas)", len(linhas),
             len({l["marca"] for l in linhas if l.get("marca")}))
    return linhas, completo


def _avisar_problema(cfg: dict, motivo: str, n: int, chrome: bool):
    from .notificar import Notificador
    onde = "robô do PC (Chrome)" if chrome else "GitHub Actions"
    conf = cfg.get("tiktok_catalogo") or {}
    texto = (f"O robô do TikTok Shop não conseguiu atualizar direito ({onde}).\n\n"
             f"Motivo: {motivo}\nProdutos coletados: {n}\n\n"
             "O que fazer:\n"
             "1. Veja o log da execução (GitHub → Actions → \"TikTok Shop (2x por dia)\").\n"
             "2. Em caso de bloqueio, aguarde a próxima rodada automática.\n"
             "3. Se aparecer 0 produtos sem bloqueio, o TikTok provavelmente mudou o site: "
             "é hora de fazer uma nova versão do bot (bot/tiktok_catalogo.py).\n\n"
             f"Mínimo esperado por rodada: {conf.get('minimo_produtos', 100)} produtos.")
    Notificador().alerta_admin(f"TikTok Shop: {motivo}", texto)


def atualizar(db, cfg: dict, agora: dt.datetime | None = None, chrome: bool = False) -> int:
    """Salva o catálogo do TikTok no banco e refaz a vitrine dos produtos afetados.

    Tenta de novo se falhar (config: tentativas, espera_entre_tentativas_min) e, se no fim
    ainda vier pouco/nada, manda um aviso pro ADMIN_EMAIL/ADMIN_WHATSAPP."""
    from .catalogo import montar_vitrine

    conf = cfg.get("tiktok_catalogo") or {}
    tentativas = max(1, int(conf.get("tentativas", 2))) if chrome else 1
    espera = float(conf.get("espera_entre_tentativas_min", 10)) * 60
    minimo = int(conf.get("minimo_produtos", 100))

    linhas, completo, erro = [], False, ""
    for t in range(1, tentativas + 1):
        agora = dt.datetime.now(dt.timezone.utc)
        try:
            linhas, completo = coletar(cfg, agora, chrome=chrome)
            erro = ""
        except Exception as e:  # noqa: BLE001
            linhas, completo, erro = [], False, f"erro no robô: {e}"
            log.exception("TikTok: tentativa %d falhou", t)
        if completo and len(linhas) >= minimo:
            break
        if t < tentativas:
            log.warning("TikTok: tentativa %d/%d trouxe %d produtos (completo=%s). Tentando de novo em %.0f min.",
                        t, tentativas, len(linhas), completo, espera / 60)
            time.sleep(espera)

    if not linhas:
        log.warning("TikTok: nada coletado; o catálogo anterior fica como está")
        db.salvar_lojas([{"nome": LOJA, "dominio": "shop.tiktok.com", "tipo": "catálogo + links",
                          "frequencia": "2x por dia", "ok": False, "atualizado_em": agora.isoformat()}])
        _avisar_problema(cfg, erro or "o TikTok bloqueou (verificação/CAPTCHA) ou o site mudou", 0, chrome)
        return 0

    antigos = db.catalogo_da_loja(LOJA)
    # A coleta por categorias é limitada. Ausência na listagem não comprova remoção.
    db.salvar_catalogo(linhas)
    grupos = {l["grupo"] for l in linhas} | {r["grupo"] for r in antigos}

    vit = montar_vitrine(db.catalogo_por_grupos(sorted(grupos)), agora)
    if vit:
        db.salvar_vitrine(vit)
    for g in grupos - {v["grupo"] for v in vit}:
        db.apagar_vitrine(g)

    db.salvar_lojas([{"nome": LOJA, "dominio": "shop.tiktok.com", "tipo": "catálogo + links",
                      "frequencia": "2x por dia", "ok": completo and len(linhas) >= minimo, "atualizado_em": agora.isoformat()}])
    log.info("TikTok: %d itens salvos, vitrine com %d produtos atualizada%s", len(linhas), len(vit),
             "" if completo else " (coleta parcial por bloqueio)")
    if not completo:
        _avisar_problema(cfg, "coleta parcial (o TikTok pediu verificação no meio)", len(linhas), chrome)
    elif len(linhas) < minimo:
        _avisar_problema(cfg, f"poucos produtos ({len(linhas)})", len(linhas), chrome)
    if not chrome and (not completo or len(linhas) < minimo):
        raise RuntimeError(f"TikTok: coleta incompleta ({len(linhas)} ofertas)")
    return len(linhas)
