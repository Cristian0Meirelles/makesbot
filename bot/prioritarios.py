"""Reconfere as variantes prioritárias mesmo sem uma inscrição ativa."""
import datetime as dt
import os
import json
from pathlib import Path

from .catalogo import linha_catalogo, montar_vitrine
from .db import SupabaseDB
from .lojas import verificar_link, _pagina_cadastrada, _LDJSON, ofertas_de_pagina, ofertas_vtex
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


def epoca():
    dominio = "www.epocacosmeticos.com.br"
    slug = "powder-blush-m-a-cblush-em-po/p"
    _, dados = _pagina_cadastrada("https://" + dominio + "/api/catalog_system/pub/products/search/" + slug)
    saida = []
    for produto in json.loads(dados):
        if normalizar(produto.get("brand")) != "mac":
            continue
        for item in produto.get("items", []):
            if item.get("itemId") != "40032" or normalizar(item.get("name")) != "film noir":
                continue
            vendedores = [v for v in item.get("sellers", []) if v.get("sellerName") == "Época Cosméticos"
                          and isinstance(v.get("commertialOffer", {}).get("IsAvailable"), bool)]
            if vendedores:
                for o in ofertas_vtex("Época Cosméticos", dominio, [dict(produto, items=[dict(item, sellers=vendedores)])]):
                    o.extra.update(produto="Powder Blush", marca="MAC", cor="Film Noir")
                    o.url = "https://" + dominio + "/" + slug + "?skuId=40032"
                    saida.append(o)
    return saida


PAGINAS = {
    "Beleza na Web": "https://www.belezanaweb.com.br/produto/mac-powder-film-noir-blush-matte-6g",
    "Zattini": "https://www.zattini.com.br/p/powder-blush-mac-blush-em-po-film-noir-incolor-M96-0424-460",
}


def powder_blush(loja):
    final, html = _pagina_cadastrada(PAGINAS[loja])
    for bruto in _LDJSON.findall(html):
        try:
            dado = json.loads(bruto)
        except ValueError:
            continue
        nos = dado if isinstance(dado, list) else dado.get("@graph", [dado])
        for no in nos:
            for item in no.get("hasVariant", [no]):
                if item.get("@type") != "Product":
                    continue
                nome = normalizar(item.get("name")).replace("m a c", "mac")
                oferta = item.get("offers")
                if not isinstance(oferta, dict) or oferta.get("seller", {}).get("name") != loja:
                    continue
                if not all(p in nome.split() for p in ("mac", "powder", "blush")) or "film noir" not in nome:
                    continue
                if item.get("url", final).rstrip("/") != final.rstrip("/"):
                    continue
                saida = ofertas_de_pagina(loja, final, '<script type="application/ld+json">' + json.dumps(item) + '</script>')
                for o in saida:
                    o.extra.update(produto="Powder Blush", marca="MAC", cor="Film Noir")
                return saida
    return []


LUSTREGLASS = "Batom Hidratante Lustreglass Mac Sheershine"
MAC_LUSTREGLASS = ("https://www.maccosmetics.com.br/product/13854/146511/produtos/maquiagem/"
                   "labios/batom/batom-hidratante-brilhante-lustreglass-sheer-shine")
BELEZA_LUSTREGLASS = "https://www.belezanaweb.com.br/produto/mac-lustreglass-sheershine-alone-time-batom-3g/"


def alone_time_mac():
    saida = []
    for oferta in verificar_link("MAC Cosmetics", MAC_LUSTREGLASS):
        if normalizar(oferta.extra.get("cor")) == "alone time":
            oferta.extra.update(categoria="Batom", produto=LUSTREGLASS)
            saida.append(oferta)
    return saida


def batons_beleza(url="https://www.belezanaweb.com.br/produto/mac-macximal-satin-film-noir-batom-acetinado-35g",
                 produto="Batom Satin MAC MACximal", termos=("macximal", "satin")):
    loja = "Beleza na Web"
    _, html = _pagina_cadastrada(url)
    saida = {}
    from .lojas import _nos
    for bruto in _LDJSON.findall(html):
        try:
            dados = json.loads(bruto)
        except ValueError:
            continue
        for item in _nos(dados):
            nome = normalizar(item.get("name")).replace("m a c", "mac")
            if not {"batom", "mac", *termos}.issubset(nome.split()):
                continue
            cor, link = item.get("color"), item.get("url") or ""
            oferta = item.get("offers")
            if not cor or not link.startswith("https://www.belezanaweb.com.br/produto/"):
                continue
            if not isinstance(oferta, dict) or oferta.get("seller", {}).get("name") != loja:
                continue
            for o in ofertas_de_pagina(loja, link, '<script type="application/ld+json">' + json.dumps(item) + '</script>'):
                o.extra.update(marca="MAC", produto=produto, cor=cor, categoria="Batom")
                saida[o.url] = o
    return list(saida.values())


def atualizar():
    fontes = [
        ("MAC · Alone Time", alone_time_mac),
        ("Beleza na Web · Lustreglass", lambda: batons_beleza(BELEZA_LUSTREGLASS, LUSTREGLASS, ("lustreglass",))),
        ("Época Cosméticos", epoca),
        ("Beleza na Web · batons", batons_beleza),
        *((loja, lambda loja=loja: powder_blush(loja)) for loja in PAGINAS),
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
    db = SupabaseDB(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    agora = dt.datetime.now(dt.timezone.utc)
    arquivo = Path(__file__).resolve().parents[1] / "config/film_noir_verificado.json"
    anteriores = json.loads(arquivo.read_text(encoding="utf-8"))
    # Inicialização idempotente. Nunca sobrescreve uma coleta posterior nem renova a data.
    db._req("POST", "catalogo?on_conflict=loja,url", json=anteriores,
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
    linhas = [linha_catalogo(o, o.extra.get("categoria", "Blush"), agora, "") for o in ofertas]
    db.salvar_catalogo(linhas)
    # Corrige a classificação anterior sem alterar o horário da última leitura.
    db._req("PATCH", "catalogo", params={"marca": "eq.MAC", "grupo": "eq.mac|batom hidratante lustreglass sheershine",
            "categoria": "eq.Outro"}, json={"categoria": "Batom"})
    # Reclassifica também a última leitura quando a loja estiver fora do ar.
    for antigo in anteriores:
        if antigo["loja"] == "MAC Cosmetics" and antigo["cor"] == "Film Noir Buff":
            db._req("PATCH", "catalogo", params={"loja": "eq.MAC Cosmetics", "url": "eq." + antigo["url"],
                    "grupo": "eq." + antigo["grupo"]}, json={"grupo": "mac|blush powder", "cor": "Film Noir",
                    "produto": "Powder Blush", "busca": antigo["busca"] + " powder blush"})
    grupos = sorted({l["grupo"] for l in linhas + anteriores} | {"mac|blush powder"})
    vitrine = montar_vitrine(db.catalogo_por_grupos(grupos), agora)
    db.salvar_vitrine(vitrine)
    for antigo in set(grupos) - {v["grupo"] for v in vitrine}:
        db.apagar_vitrine(antigo)
    print(f"Film Noir Buff: {len(linhas)} oferta(s) verificadas e vitrine atualizada.")
    if not ofertas:
        raise RuntimeError("Vitrine publicada com a última leitura. Lojas sem confirmação nova.")


if __name__ == "__main__":
    atualizar()
