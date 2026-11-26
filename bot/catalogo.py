"""
Monta o catálogo (1x por dia): varre as lojas por categoria + lançamentos e
guarda marca, produto, cor, foto, preço e estoque. O site usa isso no
autocompletar e na comparação de preços.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from collections import Counter, defaultdict

from . import lojas as L
from .classificar import chave_produto, familia_cor, tom_de_pele
from .util import Oferta, normalizar, url_codificada

log = logging.getLogger("catalogo")

# termo de busca -> categoria
TERMOS = {
    "blush": "Blush", "batom": "Batom", "gloss": "Gloss", "lip tint": "Lip tint", "lapis labial": "Lápis labial",
    "base": "Base", "corretivo": "Corretivo", "po facial": "Pó", "iluminador": "Iluminador",
    "bronzer": "Bronzer", "contorno": "Contorno", "paleta de sombras": "Sombra", "sombra": "Sombra",
    "mascara de cilios": "Máscara de cílios", "delineador": "Delineador", "sobrancelha": "Sobrancelha",
    "primer": "Primer", "fixador de maquiagem": "Fixador",
}
# palavras no nome/categoria da loja -> categoria (a ordem importa)
PISTAS = [
    ("contorno labial", "Lápis labial"), ("contorno de boca", "Lápis labial"), ("lapis de boca", "Lápis labial"),
    ("lip pencil", "Lápis labial"), ("delineador labial", "Lápis labial"), ("lapis de contorno", "Lápis labial"),
    ("lip tint", "Lip tint"), ("tint", "Lip tint"), ("gloss", "Gloss"), ("lapis labial", "Lápis labial"),
    ("lip liner", "Lápis labial"), ("batom", "Batom"), ("lipstick", "Batom"), ("blush", "Blush"),
    ("iluminador", "Iluminador"), ("highlighter", "Iluminador"), ("bronzer", "Bronzer"), ("contorno", "Contorno"),
    ("corretivo", "Corretivo"), ("concealer", "Corretivo"), ("primer", "Primer"), ("fixador", "Fixador"),
    ("setting spray", "Fixador"), ("base", "Base"), ("foundation", "Base"), ("po ", "Pó"), ("powder", "Pó"),
    ("paleta", "Sombra"), ("sombra", "Sombra"), ("eyeshadow", "Sombra"), ("mascara", "Máscara de cílios"),
    ("rimel", "Máscara de cílios"), ("delineador", "Delineador"), ("eyeliner", "Delineador"),
    ("sobrancelha", "Sobrancelha"), ("brow", "Sobrancelha"),
]
# marcas procuradas uma a uma (pega produtos que não aparecem nas buscas por tipo)
MARCAS = ["MAC", "Fenty Beauty", "Dior", "Too Faced", "Benefit", "NARS", "Rare Beauty", "Huda Beauty",
          "Charlotte Tilbury", "Urban Decay", "Clinique", "Lancôme", "Estée Lauder", "Make Up For Ever", "Bobbi Brown",
          "Bruna Tavares", "Boca Rosa", "Vult", "Ruby Rose", "Quem Disse Berenice", "Océane", "Make B", "Payot",
          "Dailus", "Mari Maria", "Latika", "Vizzela", "Franciny Ehlke", "Melu", "Catharine Hill", "Max Love",
          "Tracta", "NYX", "Maybelline", "Loreal", "Revlon", "Eudora", "Natura", "Avon", "Sephora Collection",
          "Kylie", "Anastasia Beverly Hills", "Givenchy", "Yves Saint Laurent", "Armani", "Shiseido", "Elf",
          "Makiê", "Nina Secrets", "Pausa Para Feminices", "Karen Bachini", "Jequiti", "Hinode", "Avon"]
PAGINAS_POR_TERMO = 20     # até 20 x 50 = 1000 produtos por tipo/marca em cada loja VTEX
PAGINAS_SHOPIFY = 8        # 8 x 250 produtos
LIMPAR_APOS = dt.timedelta(days=2)


# não é maquiagem (mesmo que o nome tenha "blush", "batom" etc.)
NAO_MAQUIAGEM = ["perfume", "parfum", "eau de", "toilette", "colonia", "body splash", "deo ", "desodorante",
                 "pincel", "pinceis", "esponja", "escova", "hidratante", "shampoo", "condicionador", "sabonete",
                 "necessaire", "nécessaire", "creme para", "locao", "oleo corporal", "protetor solar", "esmalte",
                 "tintura", "coloracao", "removedor", "demaquilante", "algodao", "apontador", "espelho", "organizador",
                 "estojo vazio", "mascara facial", "mascara de argila", "mascara capilar", "serum facial"]


def categoria_de(o: Oferta, termo_cat: str | None) -> str:
    nome = " " + normalizar(o.extra.get("produto") or o.titulo) + " "
    if any(" " + normalizar(x) in nome for x in NAO_MAQUIAGEM):
        return "Outro"
    texto = " " + normalizar(f"{o.extra.get('produto','')} {o.extra.get('categorias','')}") + " "
    for pista, cat in PISTAS:
        if f" {pista}" in texto:
            return cat
    return termo_cat or "Outro"


def linha_catalogo(o: Oferta, categoria: str, agora: dt.datetime, afiliado: str) -> dict:
    marca = (o.extra.get("marca") or "").strip() or None
    if marca and normalizar(marca) in ("nao disponivel", "generico", "generica", "sem marca", "outros", "outras marcas"):
        marca = None
    produto = (o.extra.get("produto") or o.titulo).strip()
    cor = (o.extra.get("cor") or "").strip() or None
    if cor and re.fullmatch(r"(\d+([.,]\d+)?\s*(un|und|unid|unidades?|ml|g|gr|kg|oz)?|[uú]nic[oa]|padr[aã]o|u|default( title)?|sem cor)", cor, re.I):
        cor = None
    url_af = afiliado.replace("{url_enc}", url_codificada(o.url)).replace("{url}", o.url) if afiliado else None
    return {
        "loja": o.loja, "marca": marca, "produto": produto[:200], "cor": cor and cor[:120],
        "categoria": categoria, "titulo": o.titulo[:300], "url": o.url, "url_afiliado": url_af,
        "imagem": o.imagem, "preco": o.preco, "disponivel": o.disponivel,
        "busca": normalizar(f"{marca or ''} {produto} {cor or ''} {categoria} {o.loja}")[:500],
        "grupo": chave_produto(marca, produto),
        "familia": familia_cor(cor, o.titulo),
        "tom": tom_de_pele(cor, categoria),
        "atualizado_em": agora.isoformat(),
    }


def varrer_loja(loja: dict, agora: dt.datetime) -> list[dict]:
    nome, dominio, tipo = loja["nome"], loja.get("dominio", ""), loja.get("tipo", "auto")
    afiliado = loja.get("afiliado") or ""
    linhas: dict[str, dict] = {}

    exigir = [normalizar(x) for x in loja.get("exigir_categoria") or []]

    def guardar(ofertas, termo_cat):
        for o in ofertas or []:
            if exigir and not any(x in normalizar(o.extra.get("categorias")) for x in exigir):
                continue  # loja de departamento: só a seção de beleza
            if o.url not in linhas:
                linhas[o.url] = linha_catalogo(o, categoria_de(o, termo_cat), agora, afiliado)

    if tipo == "mercadolivre":
        return []  # Mercado Livre tem milhões de anúncios: entra só na busca do radar

    if tipo in ("auto", "shopify"):
        try:
            for pagina in range(1, PAGINAS_SHOPIFY + 1):
                res = L.catalogo_shopify(nome, dominio, pagina)
                if res is None:
                    break
                guardar(res, None)
                if len(res) == 0:
                    break
            if linhas:
                log.info("%s (shopify): %d itens", nome, len(linhas))
                return list(linhas.values())
        except (requests.RequestException, L.LojaBloqueada) as e:
            log.info("%s shopify: %s", nome, e)

    if tipo in ("auto", "vtex"):
        try:
            if L.pagina_vtex(nome, dominio, "maquiagem", 0, 0) is None:
                log.info("%s: não é VTEX/Shopify, pulando", nome)
                return []
            guardar(L.pagina_vtex(nome, dominio, "maquiagem", 0, 49, novidades=True), None)  # lançamentos
            maximo = int(loja.get("paginas") or PAGINAS_POR_TERMO)
            buscas = list(TERMOS.items()) + [(m, None) for m in dict.fromkeys(MARCAS)]
            for termo, cat in buscas:
                for p in range(maximo):
                    try:
                        res = L.pagina_vtex(nome, dominio, termo, p * 50, p * 50 + 49)
                    except (requests.RequestException, L.LojaBloqueada) as e:
                        log.info("%s/%s: %s", nome, termo, e)
                        break
                    antes = len(linhas)
                    guardar(res, cat)
                    # parou de vir produto novo (ou acabou a lista): próxima busca
                    if not res or len(linhas) == antes or p * 50 + 50 >= 2500:
                        break
        except (requests.RequestException, L.LojaBloqueada) as e:
            log.info("%s vtex: %s", nome, e)
    log.info("%s: %d itens", nome, len(linhas))
    return list(linhas.values())


def montar_vitrine(linhas: list[dict], agora: dt.datetime) -> list[dict]:
    """Um item por produto (juntando lojas e cores): melhor preço, lojas, cores e tons."""
    grupos: dict[str, list[dict]] = defaultdict(list)
    for l in linhas:
        if l.get("categoria") and l["categoria"] != "Outro":
            grupos[l["grupo"]].append(l)
    saida = []
    for grupo, ls in grupos.items():
        disp = [l for l in ls if l["disponivel"]]
        com_preco = [l for l in (disp or ls) if l.get("preco")]
        melhor = min(com_preco, key=lambda l: l["preco"]) if com_preco else (disp or ls)[0]
        img = next((l["imagem"] for l in disp if l.get("imagem")), None) or next((l["imagem"] for l in ls if l.get("imagem")), None)
        nome = Counter(l["produto"] for l in ls).most_common(1)[0][0]
        marca = Counter(l["marca"] for l in ls if l.get("marca")).most_common(1)
        cat = Counter(l["categoria"] for l in ls).most_common(1)[0][0]
        saida.append({
            "grupo": grupo, "marca": marca[0][0] if marca else None, "nome": nome, "categoria": cat,
            "imagem": img, "preco_min": melhor.get("preco"), "loja_min": melhor["loja"],
            "url_min": melhor.get("url_afiliado") or melhor["url"],
            "lojas": sorted({l["loja"] for l in ls}), "lojas_disponiveis": sorted({l["loja"] for l in disp}),
            "n_lojas": len({l["loja"] for l in ls}), "n_cores": len({normalizar(l.get("cor")) for l in ls}),
            "disponivel": bool(disp),
            "familias": sorted({l["familia"] for l in ls if l.get("familia")}),
            "tons": sorted({l["tom"] for l in ls if l.get("tom")}),
            "busca": " ".join(sorted({w for l in ls for w in l["busca"].split()}))[:1500],
            "atualizado_em": agora.isoformat(),
        })
    return saida


def atualizar_catalogo(cfg: dict, salvar, limpar, agora: dt.datetime | None = None,
                       salvar_vitrine=None, limpar_vitrine=None) -> int:
    agora = agora or dt.datetime.now(dt.timezone.utc)
    lojas = [l for l in cfg.get("lojas", []) if l.get("ativo", True)]
    total = 0
    todas: list[dict] = []
    with ThreadPoolExecutor(4) as ex:
        for linhas in ex.map(lambda l: varrer_loja(l, agora), lojas):
            if linhas:
                salvar(linhas)
                total += len(linhas)
                todas.extend(linhas)
    # feeds oficiais de afiliados (Awin): MAC, Beleza na Web, Boticário, Natura...
    from .feeds import baixar_awin
    feed = []
    for o in baixar_awin():
        cat = categoria_de(o, None)
        if cat == "Outro":
            continue
        l = linha_catalogo(o, cat, agora, "")
        l["url_afiliado"] = o.url_afiliado
        feed.append(l)
    if feed:
        vistos = {}
        for l in feed:
            vistos[(l["loja"], l["url"])] = l
        feed = list(vistos.values())
        salvar(feed)
        todas.extend(feed)
        total += len(feed)
        log.info("Feeds de afiliados: %d itens de maquiagem", len(feed))
    # ofertas adicionadas à mão (TikTok Shop etc.)
    from .manuais import linhas_catalogo as manuais
    man = manuais(cfg, agora)
    if man:
        salvar(man)
        todas.extend(man)
        total += len(man)
        log.info("Ofertas manuais: %d", len(man))
    limpar(agora - LIMPAR_APOS)
    if salvar_vitrine:
        vit = montar_vitrine(todas, agora)
        salvar_vitrine(vit)
        if limpar_vitrine:
            limpar_vitrine(agora - dt.timedelta(seconds=1))  # tudo que não veio nesta rodada sai
        log.info("Vitrine: %d produtos (juntando lojas e cores)", len(vit))
    log.info("Catálogo atualizado: %d itens", total)
    return total
