"""
Feeds oficiais de produtos de redes de afiliados (Awin hoje; Lomadee/Rakuten depois).
Traz MAC, Beleza na Web, Boticário, Natura etc. com preço, estoque, foto e o seu link de afiliado.

Configuração (GitHub → Settings → Secrets → Actions):
  AWIN_FEED_URL  = link de download do "Create-a-Feed" da Awin (pode ser mais de um, separados por vírgula)
"""
from __future__ import annotations

import csv
import gzip
import io
import logging
import os
import zipfile

import requests

from .util import Oferta, normalizar, preco_float

log = logging.getLogger("feeds")
csv.field_size_limit(10_000_000)

# nome do anunciante na Awin -> nome da loja no site
NOMES_LOJA = {
    "mac cosmeticos br": "MAC Cosmetics", "mac cosmetics br": "MAC Cosmetics",
    "beleza na web br": "Beleza na Web", "oboticario br": "O Boticário", "o boticario br": "O Boticário",
    "eudora br": "Eudora", "natura br": "Natura", "oceane br": "Océane", "sephora br": "Sephora",
    "quem disse berenice br": "Quem Disse, Berenice?", "epoca cosmeticos br": "Época Cosméticos",
}
DOMINIOS = {
    "MAC Cosmetics": "www.maccosmetics.com.br", "Beleza na Web": "www.belezanaweb.com.br",
    "O Boticário": "www.boticario.com.br", "Eudora": "www.eudora.com.br", "Natura": "www.natura.com.br",
    "Océane": "www.oceane.com.br", "Sephora": "www.sephora.com.br",
}


def nome_loja(merchant: str) -> str:
    n = normalizar(merchant)
    if n in NOMES_LOJA:
        return NOMES_LOJA[n]
    return (merchant or "Loja").removesuffix(" BR").strip()


def _sim(v) -> bool:
    return str(v or "").strip().lower() in ("1", "yes", "y", "true", "sim", "in stock", "instock")


def _abrir(conteudo: bytes) -> str:
    if conteudo[:2] == b"\x1f\x8b":
        conteudo = gzip.decompress(conteudo)
    elif conteudo[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            conteudo = z.read(z.namelist()[0])
    return conteudo.decode("utf-8-sig", errors="replace")


def ofertas_de_csv(texto: str) -> list[Oferta]:
    amostra = texto[:5000]
    sep = "|" if amostra.count("|") > amostra.count(",") else ("\t" if "\t" in amostra.split("\n")[0] else ",")
    saida: list[Oferta] = []
    for r in csv.DictReader(io.StringIO(texto), delimiter=sep):
        g = lambda *ks: next((r[k] for k in ks if r.get(k)), "")
        loja = nome_loja(g("merchant_name"))
        url = g("merchant_deep_link", "aw_deep_link")
        afiliado = g("aw_deep_link")
        titulo = g("product_name")
        if not (url and titulo):
            continue
        estoque = g("in_stock", "is_for_sale")
        qtd = g("stock_quantity", "stock_status")
        disponivel = _sim(estoque) or (qtd.isdigit() and int(qtd) > 0) if (estoque or qtd) else True
        cor = g("colour", "color", "Fashion:colour") or None
        o = Oferta(loja, titulo, url, disponivel, g("merchant_image_url", "aw_image_url", "large_image") or None,
                   preco_float(g("search_price", "store_price", "display_price")), url_afiliado=afiliado or None,
                   extra={"marca": g("brand_name") or None, "produto": titulo, "cor": cor,
                          "categorias": f"{g('merchant_category')} {g('category_name')} {g('merchant_product_category_path')}"})
        saida.append(o)
    return saida


def baixar_awin(urls: str | None = None) -> list[Oferta]:
    urls = urls if urls is not None else os.getenv("AWIN_FEED_URL", "")
    todas: list[Oferta] = []
    for url in [u.strip() for u in urls.split(",") if u.strip()]:
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            of = ofertas_de_csv(_abrir(r.content))
            log.info("Feed Awin: %d produtos", len(of))
            todas.extend(of)
        except Exception as e:  # noqa: BLE001
            log.warning("Feed Awin falhou (%s)", type(e).__name__)
    return todas
