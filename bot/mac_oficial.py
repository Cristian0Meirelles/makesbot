"""Importa as páginas oficiais que a MAC lista nas categorias de maquiagem."""
import datetime as dt
import gzip
import json
import os
import sys
from pathlib import Path
import re
from urllib.parse import urljoin

from .db import SupabaseDB
from .catalogo import montar_vitrine
from .classificar import chave_produto
from .lojas import _pagina_cadastrada, verificar_link
from .lojas_navegador import categoria_da_url, montar_linhas

SITE = "https://www.maccosmetics.com.br"
CATEGORIAS = ("13831/produtos/maquiagem/labios", "13830/produtos/maquiagem/rosto",
              "13829/produtos/maquiagem/olhos")


def importar_leitura(db):
    arquivo = Path(__file__).resolve().parents[1] / "config/catalogo_mac_verificado.json.gz"
    with gzip.open(arquivo, "rt", encoding="utf-8") as dados:
        linhas = json.load(dados)
    grupos = {r["grupo"] for r in linhas}
    for inicio in range(0, len(linhas), 250):
        db._req("POST", "catalogo?on_conflict=loja,url", json=linhas[inicio:inicio + 250],
                headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
    # Aplica as mesmas chaves aos anúncios importados antes desta versão.
    pagina = 0
    oficiais = grupos.copy()
    while True:
        lote = db._req("GET", "catalogo", params={"marca": "eq.MAC", "select": "grupo,produto",
                       "order": "id.asc", "offset": pagina, "limit": 1000})
        for antigo, produto in {(r["grupo"], r["produto"]) for r in lote}:
            novo = chave_produto("MAC", re.sub(r"m[.·]a[.·]c", "MAC", produto, flags=re.I))
            if antigo != novo and novo in oficiais:
                db._req("PATCH", "catalogo", params={"grupo": "eq." + antigo, "marca": "eq.MAC",
                        "produto": "eq." + produto}, json={"grupo": novo})
                grupos.add(antigo)
        if len(lote) < 1000:
            break
        pagina += len(lote)
    vitrine = montar_vitrine(db.catalogo_por_grupos(sorted(grupos)), dt.datetime.now(dt.timezone.utc))
    db.salvar_vitrine(vitrine)
    for antigo in grupos - {v["grupo"] for v in vitrine}:
        db.apagar_vitrine(antigo)


def atualizar():
    db = SupabaseDB(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    if "--importar-leitura" in sys.argv:
        importar_leitura(db)
        return
    paginas = {}
    for categoria in CATEGORIAS:
        _, html = _pagina_cadastrada(f"{SITE}/products/{categoria}")
        for caminho in re.findall(r'href="(/product/\d+/(\d+)/[^"?#]+)', html):
            url, codigo = caminho
            paginas.setdefault(codigo, urljoin(SITE, url))
    agora = dt.datetime.now(dt.timezone.utc)
    total = 0
    for url in paginas.values():
        try:
            ofertas = verificar_link("MAC Cosmetics", url)
        except Exception as erro:
            print(f"::warning::{url}: {type(erro).__name__}")
            continue
        linhas = montar_linhas([(o, categoria_da_url(url)) for o in ofertas], agora)
        if linhas:
            db.salvar_catalogo(linhas)
            grupos = sorted({l["grupo"] for l in linhas})
            db.salvar_vitrine(montar_vitrine(db.catalogo_por_grupos(grupos), agora))
            total += len(linhas)
    if not total:
        raise RuntimeError("Nenhuma oferta oficial importada")
    print(f"{total} ofertas oficiais importadas.")


if __name__ == "__main__":
    atualizar()
