"""Funções pequenas usadas em todo o bot."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import quote

STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "com", "para", "pra", "the", "of", "and",
    "a", "o", "as", "os", "em", "no", "na", "cor", "tom", "ml", "g", "un", "unid",
}


def normalizar(texto: str | None) -> str:
    """'Blush Líquido — Rosé!' -> 'blush liquido rose'"""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", " ", t.lower())
    return t.strip()


def tokens(texto: str | None) -> list[str]:
    saida = []
    for t in normalizar(texto).split():
        if t in STOPWORDS:
            continue
        if len(t) < 2 and not t.isdigit():
            continue
        saida.append(t)
    return saida


def preco_float(valor) -> float | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else None
    s = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in s:  # formato brasileiro 1.234,56
        s = s.replace(".", "").replace(",", ".")
    try:
        v = float(re.sub(r"[^0-9.]", "", s) or 0)
        return v if v > 0 else None
    except ValueError:
        return None


def brl(valor: float | None) -> str:
    if not valor:
        return ""
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def url_codificada(url: str) -> str:
    return quote(url, safe="")


@dataclass
class Oferta:
    loja: str
    titulo: str
    url: str
    disponivel: bool
    imagem: str | None = None
    preco: float | None = None
    url_afiliado: str | None = None
    extra: dict = field(default_factory=dict)
