"""Importa as páginas oficiais que a MAC lista nas categorias de maquiagem."""
import datetime as dt
import os
import re
from urllib.parse import urljoin

from .db import SupabaseDB
from .catalogo import montar_vitrine
from .lojas import _pagina_cadastrada, verificar_link
from .lojas_navegador import categoria_da_url, montar_linhas

SITE = "https://www.maccosmetics.com.br"
CATEGORIAS = ("13831/produtos/maquiagem/labios", "13830/produtos/maquiagem/rosto",
              "13829/produtos/maquiagem/olhos")


def atualizar():
    db = SupabaseDB(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
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
