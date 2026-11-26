"""Reconfere as variantes prioritárias mesmo sem uma inscrição ativa."""
import datetime as dt
import os
import json

from .catalogo import linha_catalogo, montar_vitrine
from .db import SupabaseDB
from .lojas import verificar_link, _pagina_cadastrada, _LDJSON, ofertas_de_pagina
from .util import normalizar


def film_noir():
    url = ("https://www.maccosmetics.com.br/product/13842/143488/produtos/"
           "maquiagem/rosto/blush/blush-em-po-skinfinish-colourstruck")
    ofertas = verificar_link("MAC Cosmetics", url)
    return [o for o in ofertas if normalizar(o.extra.get("cor")) == "film noir buff"
            and "blush" in normalizar(o.extra.get("produto")).split()]


def blush_de_anuncio(loja, url, produto, cor):
    final, html = _pagina_cadastrada(url)
    for bruto in _LDJSON.findall(html):
        try:
            item = json.loads(bruto)
        except ValueError:
            continue
        if not isinstance(item, dict) or item.get("@type") != "Product":
            continue
        nome = normalizar(item.get("name"))
        marca = item.get("brand") or ""
        marca = marca.get("name") if isinstance(marca, dict) else marca
        if "blush" not in nome.split() or normalizar(marca) != "mac":
            continue
        if normalizar(item.get("color")) != normalizar(cor) and normalizar(cor) not in nome:
            continue
        ofertas = ofertas_de_pagina(loja, final, '<script type="application/ld+json">' + bruto + '</script>')
        for o in ofertas:
            o.extra.update(marca="MAC", produto=produto, cor=cor)
        return ofertas
    return []


def atualizar():
    fontes = [
        ("MAC Cosmetics", film_noir),
        ("Magalu", lambda: blush_de_anuncio("Magalu",
            "https://www.magazineluiza.com.br/powder-blush-mac-blush-em-po/p/ae3800ea1h/pf/pfbm/",
            "Powder Blush", "Film Noir")),
        ("Mercado Livre", lambda: blush_de_anuncio("Mercado Livre",
            "https://www.mercadolivre.com.br/blush-em-po-mac-skinfinish-colourstruck-film-noir-buff/p/MLB69093283",
            "Blush em Pó Skinfinish Colourstruck", "Film Noir Buff")),
    ]
    ofertas = []
    for loja, verificar in fontes:
        try:
            lidas = verificar()
            ofertas.extend(lidas)
            print(f"{loja}: {len(lidas)} oferta(s) confirmadas")
        except Exception as erro:
            print(f"::warning::{loja}: leitura inconclusiva ({type(erro).__name__})")
    if not ofertas:
        raise RuntimeError("Nenhuma variante prioritária confirmada nesta rodada.")
    db = SupabaseDB(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    agora = dt.datetime.now(dt.timezone.utc)
    linhas = [linha_catalogo(o, "Blush", agora, "") for o in ofertas]
    db.salvar_catalogo(linhas)
    grupos = sorted({l["grupo"] for l in linhas})
    db.salvar_vitrine(montar_vitrine(db.catalogo_por_grupos(grupos), agora))
    print(f"Film Noir Buff: {len(linhas)} oferta(s) verificadas e vitrine atualizada.")


if __name__ == "__main__":
    atualizar()
