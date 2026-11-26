"""Ofertas adicionadas à mão em config/ofertas_manuais.yaml (ex.: TikTok Shop)."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .util import Oferta, preco_float, url_codificada

log = logging.getLogger("manuais")
ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "ofertas_manuais.yaml"


def loja_do_link(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "tiktok" in host:
        # nome diferente do catálogo automático ("TikTok Shop"), senão um apagaria o outro
        return "TikTok Shop (seleção)"
    if "mercadolivre" in host or "meli.la" in host:
        return "Mercado Livre"
    if "shopee" in host:
        return "Shopee"
    if "amazon" in host:
        return "Amazon"
    return host.removeprefix("www.").split(".")[0].replace("-", " ").title()


def carregar(cfg: dict | None = None, arquivo: Path | None = None) -> list[tuple[Oferta, str]]:
    """Devolve [(Oferta, categoria)]."""
    arquivo = arquivo or ARQUIVO
    try:
        dados = yaml.safe_load(open(arquivo, encoding="utf-8")) or {}
    except FileNotFoundError:
        return []
    afiliados = (cfg or {}).get("afiliados_por_dominio") or {}
    saida = []
    for item in dados.get("ofertas") or []:
        link = str(item.get("link") or "").strip()
        if not (link.startswith("http") and item.get("marca") and item.get("produto") and item.get("categoria")):
            log.warning("Oferta manual incompleta, ignorada: %s", item)
            continue
        loja = item.get("loja") or loja_do_link(link)
        cor = str(item["cor"]).strip() if item.get("cor") else None
        titulo = f"{item['produto']}" + (f" - {cor}" if cor else "")
        afiliado = None
        host = urlparse(link).netloc.lower().removeprefix("www.")
        for dom, modelo in afiliados.items():
            if modelo and host.endswith(dom):
                if "{url}?" in modelo and "?" in link:
                    modelo = modelo.replace("{url}?", "{url}&")
                afiliado = modelo.replace("{url_enc}", url_codificada(link)).replace("{url}", link)
        o = Oferta(loja, titulo, link, bool(item.get("disponivel", True)), item.get("imagem") or None,
                   preco_float(item.get("preco")), url_afiliado=afiliado,
                   extra={"marca": str(item["marca"]), "produto": str(item["produto"]), "cor": cor, "categorias": "",
                          "manual": True})
        saida.append((o, str(item["categoria"])))
    return saida


def linhas_catalogo(cfg: dict, agora: dt.datetime) -> list[dict]:
    from .catalogo import linha_catalogo
    linhas = []
    for o, cat in carregar(cfg):
        l = linha_catalogo(o, cat, agora, "")
        l["url_afiliado"] = o.url_afiliado
        linhas.append(l)
    return linhas
