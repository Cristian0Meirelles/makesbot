"""
Leitores de loja. Cada um recebe um termo de busca (ou um link) e devolve
uma lista de Oferta(loja, titulo, url, disponivel, imagem, preco).

Tipos suportados:
  vtex           – lojas na plataforma VTEX (Boticário, QDB, Eudora, Época, ...)
  shopify        – lojas Shopify (muitas marcas independentes)
  mercadolivre   – página de busca do Mercado Livre
  auto           – tenta VTEX, depois Shopify
  link           – qualquer página de produto (lê os dados schema.org da página)
  tiktok         – link de produto do TikTok Shop (experimental)
"""
from __future__ import annotations

import html as htmlmod
import json
import logging
import re
import threading
from urllib.parse import quote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .util import Oferta, normalizar, preco_float

log = logging.getLogger("lojas")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

_local = threading.local()


class LojaBloqueada(Exception):
    """A loja recusou o acesso (403/429/captcha). Não muda o estado salvo."""


def sessao() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        retry = Retry(total=2, backoff_factor=0.6, status_forcelist=(500, 502, 503, 504),
                      allowed_methods=("GET",))
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=20))
        s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=20))
        s.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"})
        _local.s = s
    return s


def _get(url: str, *, json_=False, mobile=False, timeout=15):
    headers = {"Accept": "application/json" if json_ else "text/html,application/xhtml+xml,*/*"}
    if mobile:
        headers["User-Agent"] = UA_MOBILE
    r = sessao().get(url, headers=headers, timeout=timeout, allow_redirects=True)
    if r.status_code in (401, 403, 429):
        raise LojaBloqueada(f"{urlparse(url).netloc} respondeu {r.status_code}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    if json_:
        try:
            return r.json()
        except ValueError:
            return None
    return r.text


def _abs(dominio: str, link: str | None) -> str:
    if not link:
        return f"https://{dominio}/"
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("http"):
        return link
    return urljoin(f"https://{dominio}/", link)


# ---------------------------------------------------------------------------
# VTEX
# ---------------------------------------------------------------------------
def ofertas_vtex(loja: str, dominio: str, produtos: list) -> list[Oferta]:
    saida: list[Oferta] = []
    for p in produtos or []:
        nome = p.get("productName") or p.get("productTitle") or ""
        link = _abs(dominio, p.get("link") or (f"/{p.get('linkText')}/p" if p.get("linkText") else None))
        # a VTEX às vezes devolve o endereço interno (loja.vtexcommercestable.com.br): troca pelo domínio público
        partes = urlparse(link)
        if partes.netloc and partes.netloc != dominio and "vtex" in partes.netloc:
            link = partes._replace(netloc=dominio).geturl()
        itens = p.get("items") or []
        for item in itens:
            sku = (item.get("nameComplete") or item.get("name") or "").strip()
            titulo = nome if not sku or normalizar(sku) in normalizar(nome) else f"{nome} - {sku}"
            if normalizar(nome) and normalizar(nome) in normalizar(sku):
                titulo = sku
            imgs = item.get("images") or []
            img = imgs[0].get("imageUrl") if imgs else None
            disp, preco = False, None
            for s in item.get("sellers") or []:
                co = s.get("commertialOffer") or s.get("commercialOffer") or {}
                q = co.get("AvailableQuantity") or 0
                if co.get("IsAvailable") or q > 0:
                    disp = True
                    preco = preco_float(co.get("Price")) or preco
                    break
                preco = preco or preco_float(co.get("Price")) or preco_float(co.get("ListPrice"))
            url = link
            if len(itens) > 1 and item.get("itemId"):
                url += ("&" if "?" in url else "?") + f"skuId={item['itemId']}"
            cats = p.get("categories") or []
            cor = (item.get("name") or "").strip()
            if normalizar(nome) and normalizar(cor).startswith(normalizar(nome)):
                cor = cor[len(nome):].strip(" -–|")
            if normalizar(cor) == normalizar(nome) or normalizar(cor) in normalizar(nome):
                cor = ""
            saida.append(Oferta(loja, titulo, url, disp, img, preco, extra={
                "marca": p.get("brand"), "produto": nome,
                "cor": cor or None,
                "categorias": " ".join(c if isinstance(c, str) else str(c.get("name", "")) for c in cats),
            }))
    return saida


def pagina_vtex(loja: str, dominio: str, termo: str, de: int, ate: int, novidades=False) -> list[Oferta] | None:
    """Uma página de resultados (até 50) — usada para montar o catálogo."""
    ordem = "&O=OrderByReleaseDateDESC" if novidades else ""
    try:
        dados = _get(f"https://{dominio}/api/catalog_system/pub/products/search?ft={quote(termo)}"
                     f"&_from={de}&_to={ate}{ordem}", json_=True)
    except LojaBloqueada:
        dados = None
    if isinstance(dados, list):
        return ofertas_vtex(loja, dominio, dados)
    pagina = de // max(1, ate - de + 1) + 1
    dados = _get(f"https://{dominio}/api/io/_v/api/intelligent-search/product_search/?query={quote(termo)}"
                 f"&count={ate - de + 1}&page={pagina}&hideUnavailableItems=false"
                 + ("&sort=release:desc" if novidades else ""), json_=True)
    if isinstance(dados, dict) and isinstance(dados.get("products"), list):
        return ofertas_vtex(loja, dominio, dados["products"])
    return None


def catalogo_shopify(loja: str, dominio: str, pagina: int) -> list[Oferta] | None:
    """Catálogo inteiro de uma loja Shopify, 250 produtos por página."""
    dados = _get(f"https://{dominio}/products.json?limit=250&page={pagina}", json_=True)
    if not isinstance(dados, dict) or "products" not in dados:
        return None
    saida = []
    for p in dados["products"]:
        imgs = p.get("images") or []
        img_padrao = imgs[0].get("src") if imgs else None
        por_id = {i.get("id"): i.get("src") for i in imgs}
        link = f"https://{dominio}/products/{p.get('handle')}"
        variantes = p.get("variants") or []
        for v in variantes:
            cor = v.get("title")
            if not cor or cor.lower() in ("default title", "default"):
                cor = None
            img = por_id.get(v.get("image_id")) or (v.get("featured_image") or {}).get("src") or img_padrao
            url = link + (f"?variant={v.get('id')}" if len(variantes) > 1 else "")
            saida.append(Oferta(loja, f"{p.get('title','')}" + (f" - {cor}" if cor else ""), url,
                                bool(v.get("available")), img, preco_float(v.get("price")),
                                extra={"marca": p.get("vendor"), "produto": p.get("title", ""), "cor": cor,
                                       "categorias": f"{p.get('product_type','')} {' '.join(p.get('tags') or []) if isinstance(p.get('tags'), list) else p.get('tags','')}"}))
    return saida


def buscar_vtex(loja: str, dominio: str, termo: str) -> list[Oferta] | None:
    """None = a loja não respondeu como VTEX."""
    q = quote(termo)
    dados = None
    try:
        dados = _get(f"https://{dominio}/api/catalog_system/pub/products/search?ft={q}&_from=0&_to=29", json_=True)
    except LojaBloqueada:
        dados = None
    except requests.RequestException as e:
        log.debug("vtex legado %s: %s", dominio, e)
    if isinstance(dados, list):
        return ofertas_vtex(loja, dominio, dados)

    # busca inteligente (VTEX IO)
    try:
        dados = _get(f"https://{dominio}/api/io/_v/api/intelligent-search/product_search/"
                     f"?query={q}&count=30&hideUnavailableItems=false", json_=True)
    except requests.RequestException as e:
        log.debug("vtex IS %s: %s", dominio, e)
        dados = None
    if isinstance(dados, dict) and isinstance(dados.get("products"), list):
        return ofertas_vtex(loja, dominio, dados["products"])
    return None


# ---------------------------------------------------------------------------
# Shopify
# ---------------------------------------------------------------------------
def buscar_shopify(loja: str, dominio: str, termo: str, cor: str | None = None) -> list[Oferta] | None:
    url = (f"https://{dominio}/search/suggest.json?q={quote(termo)}"
           f"&resources[type]=product&resources[limit]=10")
    try:
        dados = _get(url, json_=True)
    except requests.RequestException:
        return None
    try:
        produtos = dados["resources"]["results"]["products"]
    except (TypeError, KeyError):
        return None
    saida: list[Oferta] = []
    for p in produtos:
        link = _abs(dominio, (p.get("url") or "").split("?")[0])
        titulo = p.get("title") or ""
        img = p.get("image") or (p.get("featured_image") or {}).get("url")
        if img and img.startswith("//"):
            img = "https:" + img
        variantes = None
        if cor and p.get("handle"):
            try:
                det = _get(f"https://{dominio}/products/{p['handle']}.js", json_=True)
                variantes = (det or {}).get("variants")
            except requests.RequestException:
                variantes = None
        if variantes:
            for v in variantes:
                vimg = (v.get("featured_image") or {}).get("src") or img
                if vimg and vimg.startswith("//"):
                    vimg = "https:" + vimg
                saida.append(Oferta(loja, f"{titulo} - {v.get('title','')}", f"{link}?variant={v.get('id')}",
                                    bool(v.get("available")), vimg, (v.get("price") or 0) / 100 or None))
        else:
            saida.append(Oferta(loja, titulo, link, bool(p.get("available")), img, preco_float(p.get("price"))))
    return saida


# ---------------------------------------------------------------------------
# Mercado Livre (página de busca)
# ---------------------------------------------------------------------------
_ML_ITEM = re.compile(r'<li[^>]+class="[^"]*ui-search-layout__item[^"]*"', re.I)
_ML_TITULO = re.compile(r'<a\b([^>]*(?:poly-component__title|ui-search-item__group__element|ui-search-link)[^>]*)>(.*?)</a>', re.S | re.I)
_ML_IMG = re.compile(r'<img\b[^>]*?(?:data-src|src)="(https://http2\.mlstatic\.com/[^"]+)"', re.I)
_ML_PRECO = re.compile(r'andes-money-amount__fraction[^>]*>([\d\.]+)<', re.I)
_ML_CENTS = re.compile(r'andes-money-amount__cents[^>]*>(\d+)<', re.I)


def buscar_mercadolivre(loja: str, termo: str, somente_oficial: bool = False) -> list[Oferta]:
    slug = normalizar(termo).replace(" ", "-")
    html = _get(f"https://lista.mercadolivre.com.br/{slug}_NoIndex_True")
    if html is None:
        return []
    if "captcha" in html.lower() and "ui-search" not in html:
        raise LojaBloqueada("Mercado Livre pediu captcha")
    return ofertas_mercadolivre_html(loja, html, somente_oficial)


def ofertas_mercadolivre_html(loja: str, html: str, somente_oficial=False) -> list[Oferta]:
    partes = _ML_ITEM.split(html)[1:] or re.split(r'class="[^"]*poly-card[^"]*"', html)[1:]
    saida: list[Oferta] = []
    vistos = set()
    for bloco in partes[:40]:
        m = _ML_TITULO.search(bloco)
        if not m:
            continue
        href = re.search(r'href="([^"]+)"', m.group(1))
        if not href:
            continue
        url = htmlmod.unescape(href.group(1)).split("#")[0]
        if "click1." in url or url in vistos:
            continue  # anúncio patrocinado / repetido
        vistos.add(url)
        titulo = htmlmod.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if somente_oficial and "loja oficial" not in bloco.lower() and "official" not in bloco.lower():
            continue
        img = _ML_IMG.search(bloco)
        pr = _ML_PRECO.search(bloco)
        preco = None
        if pr:
            preco = preco_float(pr.group(1).replace(".", ""))
            c = _ML_CENTS.search(bloco)
            if preco and c:
                preco += int(c.group(1)) / 100
        saida.append(Oferta(loja, titulo, url, True, img.group(1) if img else None, preco))
    return saida


# ---------------------------------------------------------------------------
# Link direto: qualquer página de produto com dados schema.org (JSON-LD)
# ---------------------------------------------------------------------------
_DISPONIVEIS = ("instock", "limitedavailability", "onlineonly", "instoreonly")
_LDJSON = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


def _nos(dado):
    if isinstance(dado, list):
        for d in dado:
            yield from _nos(d)
    elif isinstance(dado, dict):
        yield dado
        for chave in ("@graph", "hasVariant", "mainEntity", "itemListElement", "item"):
            if chave in dado:
                yield from _nos(dado[chave])


def _tipo(no) -> set[str]:
    t = no.get("@type")
    return {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


def _imagem(no):
    img = no.get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    if isinstance(img, dict):
        img = img.get("url") or img.get("contentUrl")
    return img


def _meta(html, prop):
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)', html, re.I) \
        or re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']', html, re.I)
    return htmlmod.unescape(m.group(1)) if m else None


def ofertas_de_pagina(loja: str, url: str, html: str) -> list[Oferta]:
    saida: list[Oferta] = []
    for bruto in _LDJSON.findall(html):
        try:
            dado = json.loads(bruto.strip())
        except ValueError:
            continue
        for no in _nos(dado):
            if "product" not in _tipo(no):
                continue
            ofertas = no.get("offers") or []
            if isinstance(ofertas, dict):
                ofertas = ofertas.get("offers") or [ofertas]
            disp, preco = False, None
            for of in ofertas if isinstance(ofertas, list) else []:
                a = str(of.get("availability") or "").lower().rsplit("/", 1)[-1]
                if a in _DISPONIVEIS:
                    disp = True
                    preco = preco_float(of.get("price") or of.get("lowPrice")) or preco
                elif preco is None:
                    preco = preco_float(of.get("price") or of.get("lowPrice"))
            titulo = no.get("name") or ""
            if titulo:
                saida.append(Oferta(loja, titulo, no.get("url") and _abs(urlparse(url).netloc, no["url"]) or url,
                                    disp, _imagem(no), preco))
    if saida:
        # página com variações: mantém só as variações se houver
        com_url_propria = [o for o in saida if o.url != url]
        return com_url_propria or saida

    # sem JSON-LD: tenta meta tags (Open Graph / Facebook catalog)
    titulo = _meta(html, "og:title")
    disp_meta = (_meta(html, "product:availability") or _meta(html, "og:availability") or "").lower()
    if titulo and disp_meta:
        return [Oferta(loja, titulo, url, disp_meta.replace(" ", "") in ("instock", "available", "in stock"),
                       _meta(html, "og:image"),
                       preco_float(_meta(html, "product:price:amount") or _meta(html, "og:price:amount")))]
    return []


def verificar_link(loja: str, url: str) -> list[Oferta]:
    html = _get(url)
    if not html:
        return []
    return ofertas_de_pagina(loja, url, html)


# ---------------------------------------------------------------------------
# TikTok Shop (experimental): lê os dados embutidos na página do produto
# ---------------------------------------------------------------------------
def verificar_tiktok(loja: str, url: str) -> list[Oferta]:
    html = _get(url, mobile=True)
    if not html:
        return []
    baixo = html.lower()
    if ("captcha" in baixo or "verify" in baixo) and "product" not in baixo:
        raise LojaBloqueada("TikTok pediu verificação")
    ofertas = ofertas_de_pagina(loja, url, html)
    if ofertas:
        return ofertas
    titulo = _meta(html, "og:title") or "Produto TikTok Shop"
    img = _meta(html, "og:image")
    estoques = [int(x) for x in re.findall(r'"(?:stock|available_stock|stock_num)"\s*:\s*(\d+)', html)]
    esgotado = bool(re.search(r'"(?:sold_out|is_sold_out)"\s*:\s*true', html)) or "esgotado" in baixo
    if estoques:
        disp = sum(estoques) > 0
    elif esgotado:
        disp = False
    else:
        raise LojaBloqueada("TikTok: não consegui ler o estoque desta página")
    return [Oferta(loja, titulo, url, disp, img, None)]
