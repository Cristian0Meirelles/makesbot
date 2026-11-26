"""
Uso:
  python -m bot.main rapido            # todas as lojas + links (menos TikTok) — roda a cada 5 min
  python -m bot.main tiktok            # só links do TikTok Shop — roda 2x por dia
  python -m bot.main tiktok_catalogo   # catálogo de maquiagem de todas as lojas do TikTok Shop — 2x por dia
  python -m bot.main tiktok_catalogo --chrome   # o mesmo, abrindo o Google Chrome do seu PC (robo-tiktok/)
  python -m bot.main saude             # relatório diário por e-mail: robôs, buscas sem resultado, pedidos sem loja
  python -m bot.main feeds             # feeds oficiais de afiliados (Awin) — 1x por hora
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
                if not res:
                    h = L._get("https://lista.mercadolivre.com.br/batom") or ""
                    print(f"   (diagnóstico ML: {len(h)} bytes, poly-card={h.count('poly-card')}, "
                          f"layout__item={h.count('ui-search-layout__item')}, "
                          f"titulo={'poly-component__title' in h}, login={'login' in h.lower()[:5000]})")
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
    ap.add_argument("modo", choices=["rapido", "tiktok", "feeds", "tudo", "catalogo", "manuais", "tiktok_catalogo", "saude", "testar"], nargs="?", default="rapido")
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--chrome", action="store_true", help="usa o Google Chrome do PC, com janela (tiktok_catalogo)")
    ap.add_argument("--sem-abrir-site", action="store_true", help="não abre o site no final (tiktok_catalogo --chrome)")
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
            # sem configuração ainda: sai sem erro para o GitHub não mandar e-mail de falha a cada 5 min
            print("⚠️  Bot ainda não configurado: faltam os Secrets SUPABASE_URL e SUPABASE_SERVICE_KEY. Veja o README.")
            return 0
        db = SupabaseDB(url, chave)

    if args.modo == "manuais":
        import datetime as dt
        from .catalogo import montar_vitrine
        from .manuais import linhas_catalogo
        agora = dt.datetime.now(dt.timezone.utc)
        linhas = linhas_catalogo(cfg, agora)
        print(f"{len(linhas)} ofertas manuais")
        if not args.seco:
            # tira do site as ofertas manuais antigas (inclusive as que foram apagadas do arquivo)
            lojas_novas = {l["loja"] for l in linhas}
            antigas = set(db.lojas_curadoria()) | lojas_novas
            grupos = {l["grupo"] for l in linhas}
            for loja in antigas:
                grupos |= {r["grupo"] for r in db.catalogo_da_loja(loja)}
                db.apagar_catalogo_da_loja(loja)
            if linhas:
                db.salvar_catalogo(linhas)
            linhas_grupos = db.catalogo_por_grupos(sorted(grupos))
            vit = montar_vitrine(linhas_grupos, agora)
            if vit:
                db.salvar_vitrine(vit)
            for g in grupos - {v["grupo"] for v in vit}:
                db.apagar_vitrine(g)
            for loja in antigas - lojas_novas:
                db.apagar_loja(loja)
            if linhas:
                db.salvar_lojas([{"nome": n, "dominio": "shop.tiktok.com" if n.startswith("TikTok Shop") else None,
                                  "tipo": "curadoria", "frequencia": "ofertas selecionadas", "ok": True,
                                  "atualizado_em": agora.isoformat()} for n in sorted(lojas_novas)])
        return 0

    if args.modo == "saude":
        from . import saude
        saude.rodar(db)
        return 0  # o aviso já foi por e-mail; não marca a Action como falha

    if args.modo == "tiktok_catalogo":
        from . import tiktok_catalogo as T
        if args.seco:
            linhas, completo = T.coletar(cfg, chrome=args.chrome)
            print(f"{len(linhas)} produtos ({'completo' if completo else 'parcial: TikTok bloqueou'})")
            for l in linhas[:30]:
                print(f"  {'✅' if l['disponivel'] else '❌'} {l['categoria']:<18} {str(l['marca'] or '-'):<18} "
                      f"{l['preco'] or '':>8}  {l['produto'][:70]}")
        else:
            n = T.atualizar(db, cfg, chrome=args.chrome)
            if args.chrome and not args.sem_abrir_site:
                import webbrowser
                site = os.getenv("SITE_URL") or "https://voltou-lilac.vercel.app"
                print(f"\n✅ {n} produtos do TikTok Shop atualizados. Abrindo o site: {site}")
                webbrowser.open(site.rstrip("/") + "/#catalogo")
        return 0

    if args.modo == "catalogo":
        from .catalogo import atualizar_catalogo
        if args.seco:
            atualizar_catalogo(cfg, lambda l: print(f"  {len(l)} itens, ex.: {l[0]['titulo']}"), lambda d: None)
        else:
            atualizar_catalogo(cfg, db.salvar_catalogo, db.limpar_catalogo, salvar_vitrine=db.salvar_vitrine,
                               limpar_vitrine=db.limpar_vitrine,
                               extras_vitrine=lambda: db.catalogo_completo_da_loja("TikTok Shop"))
        return 0

    motor = Motor(db, cfg, Notificador(seco=args.seco))
    motor.rodar(args.modo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
