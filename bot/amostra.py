"""
Gera docs/demo.json: uma amostra REAL do catálogo (produtos, fotos, preços e
estoque de verdade das lojas) para o site mostrar antes do Supabase estar ligado.

Uso: python -m bot.amostra
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import random
from collections import defaultdict
from pathlib import Path

import yaml

from .catalogo import varrer_loja

RAIZ = Path(__file__).resolve().parent.parent
MAX_LINHAS = 1500
MAX_GRUPOS_POR_LOJA = 70


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    cfg = yaml.safe_load(open(RAIZ / "config" / "lojas.yaml", encoding="utf-8"))
    agora = dt.datetime.now(dt.timezone.utc)
    lojas = [l for l in cfg["lojas"] if l.get("ativo", True)]
    todas: list[dict] = []
    for loja in lojas:
        linhas = [l for l in varrer_loja(loja, agora)
                  if l.get("imagem") and l.get("categoria") not in (None, "Outro") and l.get("preco")]
        # prefere produtos com várias cores; limita por loja para variar
        grupos = defaultdict(list)
        for l in linhas:
            grupos[l["grupo"]].append(l)
        ordem = sorted(grupos.values(), key=lambda g: (-min(len(g), 8), random.random()))
        for g in ordem[:MAX_GRUPOS_POR_LOJA]:
            todas.extend(g[:12])
    random.shuffle(todas)
    todas = todas[:MAX_LINHAS]
    campos = ("loja", "marca", "produto", "cor", "categoria", "titulo", "url", "url_afiliado", "imagem",
              "preco", "disponivel", "busca", "grupo", "atualizado_em")
    saida = {
        "gerado_em": agora.isoformat(),
        "lojas": [{"nome": l["nome"], "dominio": l["dominio"], "frequencia": "a cada 5 min", "ok": True} for l in lojas],
        "catalogo": [{k: l.get(k) for k in campos} for l in todas],
    }
    destino = RAIZ / "docs" / "demo.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"demo.json: {len(todas)} itens reais de {len({l['loja'] for l in todas})} lojas")


if __name__ == "__main__":
    main()
