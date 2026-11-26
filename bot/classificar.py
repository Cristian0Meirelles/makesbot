"""Classificações usadas nos filtros do site: família de cor, tom de pele e chave do produto."""
from __future__ import annotations

import re

from .util import normalizar, tokens

# ---------------------------------------------------------------- família de cor
FAMILIAS = [
    ("Transparente", ["transparente", "incolor", "clear", "cristal", "crystal"]),
    ("Nude", ["nude", "bege", "beige", "natural", "skin", "pele", "neutro", "neutral", "taupe", "areia", "sand"]),
    ("Rosa", ["rosa", "rose", "rosado", "pink", "blush", "chiclete", "bubble", "candy", "flamingo", "magenta", "fucsia", "pitaya"]),
    ("Vermelho", ["vermelho", "red", "ruby", "cereja", "cherry", "scarlet", "carmim", "rubi", "morango", "strawberry"]),
    ("Vinho", ["vinho", "wine", "burgundy", "berry", "plum", "ameixa", "marsala", "bordo", "uva", "grape", "amora", "cassis"]),
    ("Marrom", ["marrom", "brown", "chocolate", "cafe", "coffee", "mocha", "toffee", "caramelo", "caramel", "cacau",
                "cocoa", "canela", "cinnamon", "terracota", "terracotta", "brick", "tijolo", "mel", "honey", "avela", "hazel"]),
    ("Coral e pêssego", ["coral", "laranja", "orange", "peach", "pessego", "apricot", "damasco", "salmao", "salmon",
                         "tangerina", "papaya", "mamao", "melon", "melao"]),
    ("Roxo", ["roxo", "lilas", "purple", "violet", "violeta", "lavanda", "lavender", "orquidea", "orchid", "lilac"]),
    ("Dourado e bronze", ["dourado", "gold", "golden", "champagne", "champanhe", "bronze", "cobre", "copper", "glow", "ouro"]),
    ("Prata", ["prata", "silver", "perolado", "pearl", "perola"]),
    ("Preto", ["preto", "black", "noir", "carbon", "carvao"]),
    ("Branco", ["branco", "white", "snow", "neve"]),
    ("Azul e verde", ["azul", "blue", "verde", "green", "turquesa", "teal", "esmeralda", "emerald", "navy"]),
]
CATEGORIAS_PELE = {"Base", "Corretivo", "Pó", "Contorno", "Bronzer", "Primer"}


def familia_cor(cor: str | None, titulo: str = "") -> str | None:
    texto = " " + normalizar(f"{cor or ''}") + " "
    for nome, chaves in FAMILIAS:
        if any(f" {c} " in texto or texto.strip().startswith(c) for c in chaves):
            return nome
    if cor:
        return None
    # sem cor: tenta pelo título (ex.: "Batom Vermelho")
    texto = " " + normalizar(titulo) + " "
    for nome, chaves in FAMILIAS:
        if any(f" {c} " in texto for c in chaves):
            return nome
    return None


# ---------------------------------------------------------------- tom de pele (aproximado)
_CLARO = ("fair", "light", "claro", "clara", "claros", "porcelain", "porcelana", "ivory", "marfim", "alabaster",
          "vanilla", "baunilha", "very light", "extra light", "branca")
_MEDIO = ("medium", "medio", "media", "medios", "tan", "morena clara", "bege medio", "natural", "sand", "areia")
_ESCURO = ("deep", "dark", "escuro", "escura", "rich", "ebony", "ebano", "espresso", "mocha", "cacau", "chocolate",
           "negra", "retinta")


def tom_de_pele(cor: str | None, categoria: str | None) -> str | None:
    if categoria not in CATEGORIAS_PELE or not cor:
        return None
    n = " " + normalizar(cor) + " "
    if any(f" {k} " in n for k in _ESCURO):
        return "Escuro"
    if any(f" {k} " in n for k in _CLARO):
        return "Claro"
    if any(f" {k} " in n for k in _MEDIO):
        return "Médio"
    c = normalizar(cor).replace(" ", "")
    # códigos com letra: C10 / M20 / E30 (claro, médio, escuro)
    m = re.match(r"^(c|m|e|cl|md|es)(\d{1,3})", c)
    if m:
        return {"c": "Claro", "cl": "Claro", "m": "Médio", "md": "Médio", "e": "Escuro", "es": "Escuro"}[m.group(1)]
    # MAC NC15 / NW45 / N25 / W30
    m = re.match(r"^(nc|nw|n|w|c|wn|cn)(\d{2})", c)
    if m:
        v = int(m.group(2))
        return "Claro" if v < 25 else "Médio" if v <= 42 else "Escuro"
    # números: 100–500 (centena), 1–9 (escala decimal, ex.: Dior 2.5N)
    m = re.search(r"(\d+(?:[.,]\d)?)", cor.replace(" ", ""))
    if m:
        v = float(m.group(1).replace(",", "."))
        if v >= 100:
            return "Claro" if v < 200 else "Médio" if v < 400 else "Escuro"
        if v < 10:
            return "Claro" if v <= 2 else "Médio" if v <= 4.5 else "Escuro"
        if v < 100:
            return "Claro" if v < 25 else "Médio" if v <= 45 else "Escuro"
    return None


# ---------------------------------------------------------------- chave do produto (junta lojas diferentes)
_GENERICAS = {"maquiagem", "make", "up", "makeup", "cosmetics", "cosmeticos", "oficial", "original", "lancamento",
              "novo", "nova", "unidade", "un", "und", "refil", "kit"}
_UNIDADE = re.compile(r"^\d+([.,]\d+)?(ml|g|gr|mg|oz|un|unid|kg|l)?$")


def chave_produto(marca: str | None, produto: str) -> str:
    marca_t = set(tokens(marca))
    ts = []
    for t in tokens(produto):
        if t in marca_t or t in _GENERICAS or _UNIDADE.match(t):
            continue
        ts.append(t)
    return f"{normalizar(marca)}|{' '.join(sorted(set(ts)))}"
