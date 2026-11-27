"""Reaplica as regras às ofertas existentes sem renovar a data do estoque."""
import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor
from .catalogo import categoria_recuperada, montar_vitrine
from .classificar import tom_de_pele
from .db import SupabaseDB
from .util import normalizar


def executar():
    db = SupabaseDB(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    ultimo, total = 0, 0
    grupos = set()

    def corrigir(par):
        r, categoria = par
        db._req("PATCH", "catalogo", params={"id": "eq." + str(r["id"]), "categoria": "eq.Outro",
                "atualizado_em": "eq." + r["atualizado_em"]},
                json={"categoria": categoria, "tom": tom_de_pele(r["cor"], categoria),
                      "busca": (normalizar(categoria) + " " + (r["busca"] or ""))[:500]})

    with ThreadPoolExecutor(5) as pool:
        while True:
            lote = db._req("GET", "catalogo", params={"select": "id,produto,cor,categoria,grupo,busca,atualizado_em",
                           "id": f"gt.{ultimo}", "order": "id.asc", "limit": 1000})
            if not lote:
                break
            correcoes = []
            for r in lote:
                categoria = categoria_recuperada(r["produto"])
                if categoria and r["categoria"] in ("Outro", categoria):
                    grupos.add(r["grupo"])
                    if r["categoria"] == "Outro":
                        correcoes.append((r, categoria))
            list(pool.map(corrigir, correcoes))
            total += len(correcoes)
            ultimo = lote[-1]["id"]
    ordenados = sorted(grupos)
    for i in range(0, len(ordenados), 25):
        linhas = db.catalogo_por_grupos(ordenados[i:i + 25])
        db.salvar_vitrine(montar_vitrine(linhas, dt.datetime.now(dt.timezone.utc)))
    print(f"{total} ofertas reclassificadas; {len(grupos)} grupos revisados.")


if __name__ == "__main__":
    executar()
