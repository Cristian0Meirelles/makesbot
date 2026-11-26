"""
Robô de lojas pelo navegador (roda no PC, abrindo o Google Chrome).

Para lojas que não deixam o bot do GitHub entrar (ex.: MAC Cosmetics), este
robô abre o site no Chrome como uma pessoa faria: entra nas categorias de
maquiagem, abre cada produto, lê o que a própria página publica (nome, cor,
preço, foto, se tem estoque e o link) e salva no catálogo do Voltou!.

Ele só lê: não clica em comprar, não preenche nada, não faz login e vai com
calma entre uma página e outra. Se o site pedir verificação, ele espera você
resolver na janela (igual ao robô do TikTok).

Configuração em config/lojas.yaml -> lojas_navegador.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import random
import re
import time
from urllib.parse import urljoin, urlparse

from .catalogo import categoria_de, linha_catalogo
from .util import Oferta, normalizar, preco_float

log = logging.getLogger("navegador")

_LDJSON = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_DISPONIVEIS = ("instock", "limitedavailability", "onlineonly", "instoreonly", "presale", "preorder")
_TAMANHO = re.compile(r"^\s*\d+([.,]\d+)?\s*(ml|g|gr|oz|un|unid)\s*$", re.I)

# pedaço da URL da categoria -> categoria do site (quando o nome do produto não diz)
PISTAS_URL = [
    ("batom-liquido", "Batom"), ("batom", "Batom"), ("gloss", "Gloss"), ("lapis-labial", "Lápis labial"),
    ("lip-tint", "Lip tint"), ("blush", "Blush"), ("iluminador", "Iluminador"), ("bronz", "Bronzer"),
    ("contorno", "Contorno"), ("corretivo", "Corretivo"), ("primer", "Primer"), ("fixador", "Fixador"),
    ("base", "Base"), ("/po", "Pó"), ("sombra", "Sombra"), ("paleta", "Sombra"), ("mascara", "Máscara de cílios"),
    ("delineador", "Delineador"), ("sobrancelha", "Sobrancelha"),
]


# ---------------------------------------------------------------------------
# Partes "puras" (sem navegador) — testadas em tests/test_bot.py
# ---------------------------------------------------------------------------
def _nos(dado):
    if isinstance(dado, list):
        for x in dado:
            yield from _nos(x)
    elif isinstance(dado, dict):
        yield dado
        for v in dado.values():
            if isinstance(v, (list, dict)):
                yield from _nos(v)


def _tipos(no) -> set[str]:
    t = no.get("@type")
    return {str(x).lower() for x in (t if isinstance(t, list) else [t]) if x}


def _img(no):
    i = no.get("image")
    if isinstance(i, list):
        i = i[0] if i else None
    if isinstance(i, dict):
        i = i.get("url")
    return str(i) if i else None


def _oferta_info(no):
    ofs = no.get("offers") or []
    if isinstance(ofs, dict):
        ofs = ofs.get("offers") or [ofs]
    disp, preco, url = False, None, None
    for of in ofs if isinstance(ofs, list) else []:
        a = str(of.get("availability") or "").lower().rsplit("/", 1)[-1]
        p = preco_float(of.get("price") or of.get("lowPrice"))
        if a in _DISPONIVEIS:
            disp, preco = True, p or preco
        elif preco is None:
            preco = p
        url = url or of.get("url")
    return disp, preco, url


def cor_do_nome(variante: str, produto: str) -> str | None:
    """'Lip Tint Lustreglass - XOXO - 3ml' (produto 'Lip Tint Lustreglass') -> 'XOXO'."""
    resto = variante
    if produto and normalizar(variante).startswith(normalizar(produto)):
        resto = variante[len(produto):]
    partes = [p.strip() for p in re.split(r"\s[-–|]\s", " " + resto + " ") if p.strip()]
    partes = [p for p in partes if not _TAMANHO.match(p)]
    return partes[0] if partes else None


def ler_produto(loja: str, marca: str, url: str, html: str) -> list[Oferta]:
    """Lê o JSON-LD (schema.org) da página do produto. Uma Oferta por cor quando a página lista as cores."""
    dominio = urlparse(url).netloc
    saida: list[Oferta] = []
    for bruto in _LDJSON.findall(html):
        try:
            dado = json.loads(bruto.strip())
        except ValueError:
            continue
        for no in _nos(dado):
            tipos = _tipos(no)
            if "productgroup" in tipos or ("product" in tipos and no.get("hasVariant")):
                produto = str(no.get("name") or "").strip()
                for v in no.get("hasVariant") or []:
                    if not isinstance(v, dict):
                        continue
                    disp, preco, url_of = _oferta_info(v)
                    nome_v = str(v.get("name") or produto)
                    cor = cor_do_nome(nome_v, produto) or (str(v.get("color")) if v.get("color") else None)
                    link = urljoin(f"https://{dominio}", url_of or v.get("url") or url)
                    saida.append(Oferta(loja, f"{produto} - {cor}" if cor else produto, link, disp,
                                        _img(v) or _img(no), preco,
                                        extra={"marca": marca, "produto": produto, "cor": cor, "categorias": ""}))
                return saida  # achou o grupo com as cores: é isso
    # página sem cores: o próprio produto
    for bruto in _LDJSON.findall(html):
        try:
            dado = json.loads(bruto.strip())
        except ValueError:
            continue
        for no in _nos(dado):
            if "product" in _tipos(no) and no.get("name"):
                disp, preco, url_of = _oferta_info(no)
                produto = str(no["name"]).strip()
                return [Oferta(loja, produto, urljoin(f"https://{dominio}", url_of or no.get("url") or url), disp,
                               _img(no), preco, extra={"marca": marca, "produto": produto, "cor": None, "categorias": ""})]
    return []


def categoria_da_url(url: str) -> str | None:
    u = "/" + urlparse(url).path.lower()
    for pista, cat in PISTAS_URL:
        if pista in u:
            return cat
    return None


def montar_linhas(ofertas: list[tuple[Oferta, str | None]], agora: dt.datetime) -> list[dict]:
    linhas: dict[str, dict] = {}
    for o, dica in ofertas:
        cat = categoria_de(o, dica)
        if cat == "Outro":
            continue
        l = linha_catalogo(o, cat, agora, "")
        linhas.setdefault(l["url"], l)
    return list(linhas.values())


# ---------------------------------------------------------------------------
# Navegador
# ---------------------------------------------------------------------------
def _bloqueado(page) -> bool:
    try:
        t = (page.title() or "").lower()
        if any(x in t for x in ("access denied", "acesso negado", "just a moment", "attention required",
                                "security check", "verificação", "are you a robot")):
            return True
        corpo = page.inner_text("body", timeout=3000)[:1500].lower()
    except Exception:  # noqa: BLE001
        return False
    return ("captcha" in corpo and len(corpo) < 1200) or "verify you are human" in corpo or "access denied" in corpo


def _esperar_liberar(page, segundos: int) -> bool:
    if not _bloqueado(page):
        return True
    if segundos <= 0:
        return False
    log.warning("O site pediu verificação. Resolva na janela do Chrome (espero até %d min)...", segundos // 60)
    try:
        page.bring_to_front()
    except Exception:  # noqa: BLE001
        pass
    fim = time.time() + segundos
    while time.time() < fim:
        time.sleep(4)
        if not _bloqueado(page):
            time.sleep(2)
            return True
    return False


def _pausa(conf):
    a, b = conf.get("pausa_seg", [1.5, 3.5])
    time.sleep(random.uniform(float(a), float(b)))


def _abrir(page, url, conf, espera_verif) -> bool:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:  # noqa: BLE001
        pass
    return _esperar_liberar(page, espera_verif)


def _rolar_ate_o_fim(page, padrao: str, max_rolagens: int = 25):
    ultimo = -1
    for _ in range(max_rolagens):
        n = page.locator(f'a[href*="{padrao}"]').count()
        if n == ultimo:
            break
        ultimo = n
        page.mouse.wheel(0, 4000)
        time.sleep(1.2)
        # botão "carregar mais"/"ver mais", se a loja tiver
        for nome in ("Carregar mais", "Ver mais", "Mostrar mais", "Load more"):
            b = page.get_by_role("button", name=nome)
            if b.count():
                try:
                    b.first.click(timeout=3000)
                    time.sleep(1.5)
                except Exception:  # noqa: BLE001
                    pass


def _links(page, seletor_regex: str, dominio: str) -> list[str]:
    hrefs = page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => a.href)")
    rx = re.compile(seletor_regex)
    saida = []
    for h in hrefs:
        h = h.split("#")[0]
        if urlparse(h).netloc.endswith(dominio.removeprefix("www.")) and rx.search(h):
            saida.append(h.split("?")[0])
    return list(dict.fromkeys(saida))


def coletar_loja(page, loja: dict, agora: dt.datetime, espera_verif: int) -> tuple[list[dict], bool]:
    nome, marca, dominio = loja["nome"], loja.get("marca") or loja["nome"], loja["dominio"]
    inicio = loja.get("inicio") or f"https://{dominio}/"
    padrao_cat = loja.get("padrao_categoria") or r"/(maquiagem|makeup)/"
    padrao_prod = loja.get("padrao_produto") or r"/product/"
    max_prod = int(loja.get("max_produtos", 800))

    if not _abrir(page, inicio, loja, espera_verif):
        log.warning("%s: bloqueado na página inicial", nome)
        return [], False
    categorias = list(dict.fromkeys((loja.get("categorias") or []) + _links(page, padrao_cat, dominio)))
    log.info("%s: %d categorias de maquiagem", nome, len(categorias))

    produtos: dict[str, str | None] = {}
    completo = True
    for cat_url in categorias:
        _pausa(loja)
        if not _abrir(page, cat_url, loja, espera_verif):
            completo = False
            log.warning("%s: bloqueado em %s", nome, cat_url)
            break
        _rolar_ate_o_fim(page, loja.get("trecho_produto") or "/product")
        novos = 0
        for p in _links(page, padrao_prod, dominio):
            if p not in produtos:
                produtos[p] = categoria_da_url(cat_url)
                novos += 1
        log.info("%s: %s -> %d produtos novos", nome, urlparse(cat_url).path, novos)
        if len(produtos) >= max_prod:
            break

    ofertas: list[tuple[Oferta, str | None]] = []
    for i, (url, dica) in enumerate(list(produtos.items())[:max_prod], 1):
        _pausa(loja)
        try:
            if not _abrir(page, url, loja, espera_verif):
                completo = False
                log.warning("%s: bloqueado nos produtos (%d/%d)", nome, i, len(produtos))
                break
            achados = ler_produto(nome, marca, url, page.content())
        except Exception as e:  # noqa: BLE001
            log.info("%s: erro em %s: %s", nome, url, e)
            continue
        ofertas += [(o, dica or categoria_da_url(url)) for o in achados]
        if i % 25 == 0:
            log.info("%s: %d/%d produtos lidos", nome, i, len(produtos))
    linhas = montar_linhas(ofertas, agora)
    log.info("%s: %d ofertas (cores) de maquiagem em %d produtos", nome, len(linhas), len(produtos))
    return linhas, completo


def atualizar(db, cfg: dict, chrome: bool = True, so_loja: str | None = None) -> int:
    from playwright.sync_api import sync_playwright
    from . import tiktok_catalogo as T
    from .catalogo import montar_vitrine
    from .notificar import Notificador

    conf = cfg.get("lojas_navegador") or {}
    lojas = [l for l in conf.get("lojas") or [] if l.get("ativo", True)]
    if so_loja:
        lojas = [l for l in lojas if normalizar(l["nome"]) == normalizar(so_loja)]
    espera = int(conf.get("esperar_verificacao_min", 10)) * 60 if chrome else 0
    total = 0
    with sync_playwright() as pw:
        browser, ctx = T._abrir_navegador(pw, chrome)
        page = ctx.pages[0] if chrome and ctx.pages else ctx.new_page()
        try:
            for loja in lojas:
                agora = dt.datetime.now(dt.timezone.utc)
                try:
                    linhas, completo = coletar_loja(page, loja, agora, espera)
                except Exception as e:  # noqa: BLE001
                    log.exception("%s: falhou", loja["nome"])
                    linhas, completo = [], False
                    erro = str(e)
                else:
                    erro = ""
                minimo = int(loja.get("minimo_ofertas", 50))
                if linhas:
                    antigos = db.catalogo_da_loja(loja["nome"])
                    grupos = {l["grupo"] for l in linhas} | {r["grupo"] for r in antigos}
                    db.salvar_catalogo(linhas)  # o que sumir do site sai sozinho em 2 dias (limpeza do catálogo)
                    vit = montar_vitrine(db.catalogo_por_grupos(sorted(grupos)), agora)
                    if vit:
                        db.salvar_vitrine(vit)
                    total += len(linhas)
                db.salvar_lojas([{"nome": loja["nome"], "dominio": loja["dominio"], "tipo": "navegador (PC)",
                                  "frequencia": "2x por dia", "ok": bool(linhas) and completo,
                                  "atualizado_em": agora.isoformat()}])
                if not completo or len(linhas) < minimo:
                    motivo = erro or ("o site pediu verificação e ninguém resolveu" if not completo
                                      else f"poucas ofertas ({len(linhas)})")
                    Notificador().alerta_admin(
                        f"{loja['nome']}: {motivo}",
                        f"O robô do navegador não conseguiu ler a {loja['nome']} direito.\n\nMotivo: {motivo}\n"
                        f"Ofertas lidas: {len(linhas)} (mínimo esperado: {minimo})\n\n"
                        "Se o motivo for verificação, rode robo-tiktok\\rodar.bat e resolva na janela.\n"
                        "Se vier 0 sem verificação, o site mudou e precisamos de uma nova versão do robô "
                        "(bot/lojas_navegador.py / config lojas_navegador).")
        finally:
            browser.close()
    return total
