"""
Uso:
  python -m bot.main rapido            # todas as lojas + links (menos TikTok) — roda a cada 5 min
  python -m bot.main tiktok            # só links do TikTok Shop — roda 2x por dia
  python -m bot.main catalogo          # atualiza o catálogo do autocompletar — 1x por dia
  python -m bot.main testar            # mostra quais lojas estão respondendo
  python -m bot.main testar --email voce@gmail.com --whatsapp 5511999999999 --callmebot 123456
Opções:
  --seco    não envia nada e não precisa de Supabase (usa um produto de exemplo)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import yaml

from . import lojas as L
from .db import MemDB, SupabaseDB
from .motor import Motor
from .notificar import Notificador

RAIZ = Path(__file__).resolve().parent.parent


def carregar_config() -> dict:
    with open(RAIZ / "config" / "lojas.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def produto_exemplo():
    return [{
        "id": "exemplo", "categoria": "Blush", "marca": "MAC", "nome": "Blush Powder", "cor": None,
        "links": [], "disponivel": False, "imagem_loja": None, "foto_url": None,
        "inscricoes": [{"id": "i1", "email": "teste@exemplo.com", "whatsapp": None, "token": "t", "ativo": True}],
    }]


def testar(cfg: dict, args) -> int:
    print("\n=== Teste das lojas (busca: 'batom') ===")
    for loja in cfg.get("lojas", []):
        if not loja.get("ativo", True):
            continue
        t0 = time.time()
        try:
            if loja.get("tipo") == "mercadolivre":
                res, tipo = L.buscar_mercadolivre(loja["nome"], "batom"), "mercadolivre"
            else:
                res, tipo = None, None
                if loja.get("tipo", "auto") in ("vtex", "auto"):
                    res = L.buscar_vtex(loja["nome"], loja["dominio"], "batom")
                    tipo = "vtex" if res is not None else None
                if res is None and loja.get("tipo", "auto") in ("shopify", "auto"):
                    res = L.buscar_shopify(loja["nome"], loja["dominio"], "batom")
                    tipo = "shopify" if res is not None else None
            if res is None:
                print(f"❌ {loja['nome']:<24} não respondeu como VTEX/Shopify — use links diretos para ela")
            else:
                disp = sum(o.disponivel for o in res)
                ex = res[0].titulo[:50] if res else "-"
                print(f"✅ {loja['nome']:<24} {tipo:<12} {len(res):>3} resultados ({disp} disponíveis) "
                      f"{time.time()-t0:.1f}s  ex.: {ex}")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  {loja['nome']:<24} erro: {e}")

    n = Notificador()
    prod = {"id": "x", "marca": "MAC", "nome": "Teste do bot", "cor": "", "imagem_loja": None}
    achado = [{"loja": "Loja Teste", "url": n.site or "https://github.com", "preco": 99.9, "imagem": None}]
    if args.email:
        ok, erro = n.enviar_email(args.email, "💄 Teste do Voltou!", n.html_email(prod, achado, None),
                                  n.texto_whatsapp(prod, achado, None))
        print(f"\nE-mail de teste para {args.email}: {'✅ enviado' if ok else '❌ ' + erro}")
    if args.whatsapp:
        ok, erro = n.enviar_whatsapp(args.whatsapp, n.texto_whatsapp(prod, achado, None), args.callmebot or None)
        print(f"WhatsApp de teste para {args.whatsapp}: {'✅ enviado' if ok else '❌ ' + erro}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["rapido", "tiktok", "tudo", "catalogo", "testar"], nargs="?", default="rapido")
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--email")
    ap.add_argument("--whatsapp")
    ap.add_argument("--callmebot")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cfg = carregar_config()

    if args.modo == "testar":
        return testar(cfg, args)

    if args.seco:
        db = MemDB(produto_exemplo())
    else:
        url, chave = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
        if not (url and chave):
            print("Faltam SUPABASE_URL e SUPABASE_SERVICE_KEY (Secrets do GitHub).", file=sys.stderr)
            return 1
        db = SupabaseDB(url, chave)

    if args.modo == "catalogo":
        from .catalogo import atualizar_catalogo
        if args.seco:
            atualizar_catalogo(cfg, lambda l: print(f"  {len(l)} itens, ex.: {l[0]['titulo']}"), lambda d: None)
        else:
            atualizar_catalogo(cfg, db.salvar_catalogo, db.limpar_catalogo)
        return 0

    motor = Motor(db, cfg, Notificador(seco=args.seco))
    motor.rodar(args.modo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
