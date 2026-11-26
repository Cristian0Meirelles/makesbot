"""
Relatório diário para o dono do site (roda depois do catálogo, 1x por dia):
  - os robôs estão funcionando? (TikTok Shop, lojas, feeds)
  - quantos produtos/ofertas tem no site
  - o que as pessoas procuraram e NÃO acharam (buscas_vazias)
  - pedidos do radar que ainda não acharam loja
Manda por e-mail (ADMIN_EMAIL). Se algum robô estiver com problema, o assunto avisa.
"""
from __future__ import annotations

import datetime as dt
import logging

from .notificar import Notificador

log = logging.getLogger("saude")

TIKTOK_MAX_HORAS = 26  # roda 2x por dia; mais que isso sem atualizar = problema


def _quando(iso: str | None, agora: dt.datetime) -> tuple[str, float]:
    if not iso:
        return "nunca", 1e9
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    h = (agora - t).total_seconds() / 3600
    return (f"há {h:.0f} h" if h >= 1 else "há menos de 1 h"), h


def montar_relatorio(db, agora: dt.datetime | None = None) -> tuple[str, str, bool]:
    """Devolve (assunto, texto, tem_problema)."""
    agora = agora or dt.datetime.now(dt.timezone.utc)
    problemas: list[str] = []
    linhas: list[str] = []

    lojas = db.lojas_todas()
    tiktok = next((l for l in lojas if l.get("nome") == "TikTok Shop"), None)
    quando, horas = _quando((tiktok or {}).get("atualizado_em"), agora)
    if not tiktok or horas > TIKTOK_MAX_HORAS:
        problemas.append(f"TikTok Shop sem atualizar ({quando}). Rode robo-tiktok\\rodar.bat no PC "
                         "ou veja o log da Action \"TikTok Shop (2x por dia)\". Se continuar, precisa de nova versão do bot.")
    elif tiktok.get("ok") is False:
        problemas.append(f"TikTok Shop: última rodada com bloqueio/parcial ({quando}).")
    linhas.append(f"TikTok Shop: atualizado {quando}, status {'ok' if (tiktok or {}).get('ok') else 'com problema'}")

    fora = [l["nome"] for l in lojas if l.get("ok") is False and l.get("nome") != "TikTok Shop"]
    if fora:
        problemas.append(f"Lojas sem responder: {', '.join(sorted(fora))}")
    linhas.append(f"Lojas cadastradas: {len(lojas)} ({len(lojas) - len(fora)} respondendo)")

    n_cat = db.contar("catalogo")
    n_vit = db.contar("vitrine")
    n_tt = db.contar("catalogo", {"loja": "eq.TikTok Shop"})
    linhas.append(f"Catálogo: {n_vit or 0:,} produtos na vitrine, {n_cat or 0:,} ofertas (cada cor em cada loja), "
                  f"{n_tt or 0:,} do TikTok Shop".replace(",", "."))

    buscas = db.buscas_vazias_desde(agora - dt.timedelta(days=7))
    linhas.append("")
    linhas.append("O QUE PROCURARAM E NÃO ACHARAM (últimos 7 dias):")
    if buscas:
        for b in buscas:
            linhas.append(f"  {b['vezes']:>3}x  {b['termo']}")
    else:
        linhas.append("  nada registrado (ou o SQL supabase/003_buscas_e_saude.sql ainda não foi rodado)")

    pend = db.produtos_sem_oferta()
    linhas.append("")
    linhas.append("PEDIDOS DO RADAR AINDA SEM LOJA (os mais novos):")
    if pend:
        for p in pend:
            nome = " ".join(x for x in [p.get("marca"), p.get("nome"), p.get("cor")] if x)
            link = (p.get("links") or [None])[0]
            linhas.append(f"  - {nome}" + (f"  ({link})" if link else ""))
    else:
        linhas.append("  nenhum")

    texto = ""
    if problemas:
        texto += "⚠️ PRECISA DE ATENÇÃO:\n" + "\n".join(f"- {p}" for p in problemas) + "\n\n"
    texto += "\n".join(linhas)
    assunto = ("⚠️ problema nos robôs" if problemas else "relatório do dia") + f" ({agora:%d/%m})"
    return assunto, texto, bool(problemas)


def rodar(db) -> int:
    assunto, texto, problema = montar_relatorio(db)
    print(texto)
    Notificador().alerta_admin(assunto, texto)
    return 1 if problema else 0
