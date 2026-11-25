"""Decide se um resultado de busca de uma loja é o produto que a pessoa quer."""
from __future__ import annotations

from .util import tokens

# palavras que indicam que o resultado NÃO é o produto em si
PALAVRAS_EXCLUIDAS = {"kit", "refil", "miniatura", "mini", "tester", "amostra", "pincel", "estojo", "case"}


def _presente(token: str, conjunto: set[str]) -> bool:
    if token in conjunto:
        return True
    # tolera plural/variações: blush ~ blushes, batom ~ batons
    if len(token) >= 4:
        for t in conjunto:
            if len(t) >= 4 and (t.startswith(token) or token.startswith(t)):
                return True
    return False


def combina(produto: dict, titulo: str, loja_da_marca: bool = False) -> bool:
    """
    produto: {'marca', 'nome', 'cor'}
    titulo:  texto do resultado (nome do produto + nome da variação/cor)
    loja_da_marca: True quando a loja é da própria marca (ex.: site da MAC),
                   aí a marca não precisa aparecer no título.
    """
    t = set(tokens(titulo))
    nome = tokens(produto.get("nome"))
    marca = tokens(produto.get("marca"))
    cor = tokens(produto.get("cor"))

    if not nome or not t:
        return False

    # nome: todas as palavras (aceita 1 faltando se o nome for comprido)
    faltando = [x for x in nome if not _presente(x, t)]
    if len(faltando) > (1 if len(nome) >= 4 else 0):
        return False

    # marca: pelo menos uma palavra da marca, exceto em loja da própria marca
    if marca and not loja_da_marca and not any(_presente(m, t) for m in marca):
        return False

    # cor/tom: todas as palavras
    if cor and not all(_presente(c, t) for c in cor):
        return False

    # evita kits, refis, miniaturas — a menos que a pessoa tenha pedido isso
    pedido = set(nome) | set(cor)
    if (t & PALAVRAS_EXCLUIDAS) - pedido:
        return False

    return True
