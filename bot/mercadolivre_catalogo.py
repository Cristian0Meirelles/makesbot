"""Coleta diária independente das lojas oficiais do Mercado Livre."""
import datetime as dt
import os
import logging
from .catalogo import montar_vitrine, varrer_loja
from .db import SupabaseDB
from .main import carregar_config


def atualizar():
    loja = next(l for l in carregar_config()["lojas"] if l["tipo"] == "mercadolivre")
    if not loja.get("ativo", True):
        return
    agora = dt.datetime.now(dt.timezone.utc)
    db = SupabaseDB(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    linhas = varrer_loja(loja, agora)
    if linhas:
        db.salvar_catalogo(linhas)
        grupos = sorted({r["grupo"] for r in linhas})
        db.salvar_vitrine(montar_vitrine(db.catalogo_por_grupos(grupos), agora))
    db.salvar_lojas([{"nome": loja["nome"], "dominio": loja["dominio"], "tipo": loja["tipo"],
                      "frequencia": "diária", "ok": bool(linhas), "atualizado_em": agora.isoformat()}])
    if not linhas:
        raise RuntimeError("Coleta executada sem ofertas confirmadas")
    print(f"{len(linhas)} ofertas coletadas")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    atualizar()
