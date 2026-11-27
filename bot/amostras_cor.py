"""Lê as amostras digitais publicadas para os SKUs das páginas oficiais."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .lojas import _pagina_cadastrada
from .util import normalizar

DOCS = Path(__file__).resolve().parents[1] / "docs"


def amostras_mac(url):
    _, html = _pagina_cadastrada(url)
    codigo = re.search(r"/product/\d+/(\d+)/", url)[1]
    script = re.search(r'<script\b[^>]*\bid="page_data"[^>]*>(.*?)</script>', html, re.S)
    if not script:
        return {}
    pilha = [json.loads(script[1])]
    cores = {}
    while pilha:
        item = pilha.pop()
        if isinstance(item, list):
            pilha.extend(item)
        elif isinstance(item, dict):
            pilha.extend(item.values())
            hex_cor = str(item.get("HEX_VALUE") or "").strip().lstrip("#").lower()
            nome = item.get("SHADENAME")
            if nome and item.get("PRODUCT_ID") == "PROD" + codigo and re.fullmatch("[0-9a-f]{6}", hex_cor):
                cores[normalizar(nome)] = hex_cor
    return cores


if __name__ == "__main__":
    marca = next(m for m in json.loads((DOCS / "oficiais.json").read_text())["marcas"] if m["marca"] == "MAC")
    produtos = dict(marca["produtos"])
    for r in json.loads((DOCS.parent / "config/film_noir_verificado.json").read_text()):
        if r["loja"] == "MAC Cosmetics":
            produtos[r["grupo"]] = r["url"].split("?")[0]
    urls = sorted(set(produtos.values()))
    with ThreadPoolExecutor(4) as pool:
        paletas = dict(zip(urls, pool.map(amostras_mac, urls)))
    indice = {grupo: {"fonte": url, "tons": paletas[url]} for grupo, url in produtos.items() if paletas[url]}
    (DOCS / "amostras-cor.json").write_text(json.dumps(indice, ensure_ascii=False, sort_keys=True) + "\n")
    print(len(indice), "modelos com amostras")
