"""
O coração do bot: busca cada produto pedido em cada loja, salva as ofertas
e avisa as pessoas SOMENTE quando uma loja passa de "esgotado" para "disponível".
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from . import lojas as L
from .catalogo import linha_catalogo
from .matcher import combina
from .util import Oferta, normalizar, tokens, url_codificada

log = logging.getLogger("motor")

RESFRIAMENTO = dt.timedelta(hours=12)   # não repete aviso da mesma loja para a mesma pessoa
MAX_OFERTAS_POR_LOJA = 6


def eh_tiktok(url: str) -> bool:
    return "tiktok" in urlparse(url).netloc.lower()


class Motor:
    def __init__(self, db, config: dict, notificador, agora: dt.datetime | None = None, trabalhadores: int = 8):
        self.db = db
        self.cfg = config
        self.notif = notificador
        self.agora = agora or dt.datetime.now(dt.timezone.utc)
        self.trabalhadores = trabalhadores
        self.lojas = [l for l in config.get("lojas", []) if l.get("ativo", True)]
        self._cache: dict = {}
        self._cache_lock = threading.Lock()
        self._tipo_detectado: dict[str, str] = {}
        self._status_loja: dict[str, bool] = {}
        self._dominio_sem: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(3))

    # ------------------------------------------------------------------ busca
    def _buscar_loja(self, loja: dict, termo: str, cor: str | None) -> list[Oferta]:
        nome, dominio, tipo = loja["nome"], loja.get("dominio", ""), loja.get("tipo", "auto")
        chave = (nome, normalizar(termo), normalizar(cor) if tipo != "vtex" else "")
        with self._cache_lock:
            if chave in self._cache:
                return self._cache[chave]
        with self._dominio_sem[dominio]:
            if tipo == "mercadolivre":
                res = L.buscar_mercadolivre(nome, termo, loja.get("somente_oficial", False))
            else:
                tipo = self._tipo_detectado.get(nome, tipo)
                res = None
                if tipo in ("vtex", "auto"):
                    res = L.buscar_vtex(nome, dominio, termo)
                    if res is not None:
                        self._tipo_detectado[nome] = "vtex"
                if res is None and tipo in ("shopify", "auto"):
                    res = L.buscar_shopify(nome, dominio, termo, cor)
                    if res is not None:
                        self._tipo_detectado[nome] = "shopify"
                if res is None:
                    raise L.LojaBloqueada(f"{nome}: busca não suportada ({tipo})")
        with self._cache_lock:
            self._cache[chave] = res
        return res

    def _loja_da_marca(self, loja: dict, produto: dict) -> bool:
        marca = normalizar(produto.get("marca"))
        return any(normalizar(m) == marca or (normalizar(m) and normalizar(m) in marca)
                   for m in loja.get("marcas") or [])

    def _termo(self, loja: dict, produto: dict) -> str:
        if self._loja_da_marca(loja, produto):
            return produto["nome"]
        return f"{produto['marca']} {produto['nome']}"

    def _nome_loja_link(self, url: str) -> str:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        for l in self.cfg.get("lojas", []):
            if l.get("dominio", "").lower().removeprefix("www.") == host:
                return l["nome"]
        if "tiktok" in host:
            return "TikTok Shop"
        if "amazon" in host:
            return "Amazon"
        if "mercadolivre" in host or "mercadolibre" in host:
            return "Mercado Livre"
        base = host.split(".")[0]
        return base.replace("-", " ").title()

    def _afiliar(self, loja_nome: str, url: str) -> str | None:
        modelo = ""
        for l in self.cfg.get("lojas", []):
            if l["nome"] == loja_nome:
                modelo = l.get("afiliado") or ""
        if not modelo:
            host = urlparse(url).netloc.lower().removeprefix("www.")
            for dom, m in (self.cfg.get("afiliados_por_dominio") or {}).items():
                if m and host.endswith(dom):
                    modelo = m
        if not modelo:
            return None
        if "{url}?" in modelo and "?" in url:
            modelo = modelo.replace("{url}?", "{url}&")
        return modelo.replace("{url_enc}", url_codificada(url)).replace("{url}", url)

    # ------------------------------------------------------------------ tarefas
    def _feed_por_loja(self) -> dict[str, list[Oferta]]:
        if not hasattr(self, "_feed_cache"):
            from .feeds import baixar_awin
            grupos: dict[str, list[Oferta]] = defaultdict(list)
            for o in baixar_awin():
                grupos[o.loja].append(o)
            self._feed_cache = dict(grupos)
        return self._feed_cache

    def _tarefas(self, modo: str, alvos: list[dict]):
        """Gera (produto, nome_loja, função)."""
        if modo in ("feeds", "tudo"):
            for loja, ofertas in self._feed_por_loja().items():
                for p in alvos:
                    da_marca = bool(normalizar(p.get("marca")) and normalizar(p.get("marca")).split()[0] in normalizar(loja))
                    yield p, loja, (lambda ofertas=ofertas, p=p, da_marca=da_marca:
                                    [o for o in ofertas if combina(p, f"{o.titulo} {o.extra.get('cor') or ''}", da_marca)])
            if modo == "feeds":
                return
        for p in alvos:
            if modo in ("rapido", "tudo"):
                for loja in self.lojas:
                    termo = self._termo(loja, p)
                    yield p, loja["nome"], (lambda loja=loja, termo=termo, p=p:
                                             [o for o in self._buscar_loja(loja, termo, p.get("cor"))
                                              if combina(p, o.titulo, self._loja_da_marca(loja, p))])
            for link in p.get("links") or []:
                tiktok = eh_tiktok(link)
                if (modo == "tiktok" and not tiktok) or (modo == "rapido" and tiktok):
                    continue
                nome = self._nome_loja_link(link)
                fn = L.verificar_tiktok if tiktok else L.verificar_link
                yield p, nome, (lambda fn=fn, nome=nome, link=link, p=p: self._filtrar_link(p, fn(nome, link)))

    def _filtrar_link(self, produto: dict, ofertas: list[Oferta]) -> list[Oferta]:
        """Link colado pela pessoa: confia no link, mas se a página tiver várias cores, filtra pela cor."""
        cor = tokens(produto.get("cor"))
        if cor and len(ofertas) > 1:
            com_cor = [o for o in ofertas if all(c in tokens(o.titulo) for c in cor)]
            if com_cor:
                return com_cor
        return ofertas

    # ------------------------------------------------------------------ execução
    def rodar(self, modo: str = "rapido") -> dict:
        alvos = self.db.alvos()
        log.info("Modo %s: %d produtos com alguém esperando, %d lojas", modo, len(alvos), len(self.lojas))
        if not alvos:
            self._salvar_lojas(modo)
            return {"produtos": 0, "avisos": 0}

        tarefas = list(self._tarefas(modo, alvos))
        resultados: dict[tuple[str, str], list[Oferta] | Exception] = {}

        def executar(t):
            p, nome, fn = t
            try:
                res = fn()
                self._status_loja[nome] = True
            except Exception as e:  # noqa: BLE001
                res = e
                self._status_loja.setdefault(nome, False)
                log.info("  %s / %s: %s", nome, p["nome"], e)
            return (p["id"], nome), res

        with ThreadPoolExecutor(self.trabalhadores) as ex:
            for chave, res in ex.map(executar, tarefas):
                anterior = resultados.get(chave)
                if isinstance(anterior, list) and isinstance(res, list):
                    resultados[chave] = anterior + res      # loja + link da mesma loja
                elif isinstance(anterior, list):
                    pass                                    # mantém o que funcionou
                else:
                    resultados[chave] = res

        anteriores = self.db.ofertas_por_produto([p["id"] for p in alvos])
        total_avisos = 0
        for p in alvos:
            total_avisos += self._processar_produto(p, resultados, anteriores.get(p["id"], []))
        self._salvar_lojas(modo)
        log.info("Fim: %d avisos enviados", total_avisos)
        return {"produtos": len(alvos), "avisos": total_avisos}

    def _processar_produto(self, p: dict, resultados: dict, ofertas_antes: list[dict]) -> int:
        antes_disp: dict[str, bool] = defaultdict(bool)
        for o in ofertas_antes:
            antes_disp[o["loja"]] |= bool(o.get("disponivel"))
        estado_final = dict(antes_disp)
        imagem = None
        novidades: list[dict] = []

        for (pid, loja), res in resultados.items():
            if pid != p["id"] or isinstance(res, Exception):
                continue  # erro: não mexe no estado salvo dessa loja
            # disponíveis primeiro, depois mais baratos; sem repetir URL
            vistos, unicas = set(), []
            for o in sorted(res, key=lambda o: (not o.disponivel, o.preco or 1e9)):
                if o.url not in vistos:
                    vistos.add(o.url)
                    unicas.append(o)
            top = unicas[:MAX_OFERTAS_POR_LOJA]
            linhas = []
            for o in top:
                o.url_afiliado = o.url_afiliado or self._afiliar(loja, o.url)
                linhas.append({"produto_id": p["id"], "loja": loja, "titulo": o.titulo[:300], "url": o.url,
                               "url_afiliado": o.url_afiliado, "imagem": o.imagem, "preco": o.preco,
                               "disponivel": o.disponivel, "atualizado_em": self.agora.isoformat()})
                imagem = imagem or o.imagem
            self.db.substituir_ofertas(p["id"], loja, linhas)
            # mantém o catálogo do site fresquinho para os produtos mais procurados
            cat = [linha_catalogo(o, p.get("categoria") or "Outro", self.agora, "")
                   | {"url_afiliado": o.url_afiliado} for o in top if o.extra.get("produto")]
            if cat and hasattr(self.db, "salvar_catalogo"):
                try:
                    self.db.salvar_catalogo(cat)
                except Exception as e:  # noqa: BLE001
                    log.debug("catálogo: %s", e)
            agora_disp = any(o.disponivel for o in top)
            estado_final[loja] = agora_disp
            if agora_disp and not antes_disp.get(loja):
                melhor = next(l for l in linhas if l["disponivel"])
                novidades.append(melhor)

        disponivel = any(estado_final.values())
        campos = {"ultima_verificacao": self.agora.isoformat(), "disponivel": disponivel}
        if imagem and not p.get("imagem_loja"):
            campos["imagem_loja"] = imagem
        if disponivel and not p.get("disponivel"):
            campos["disponivel_desde"] = self.agora.isoformat()
        if not disponivel:
            campos["disponivel_desde"] = None
        self.db.atualizar_produto(p["id"], campos)

        if not novidades:
            return 0
        log.info("✨ %s %s voltou em: %s", p["marca"], p["nome"], ", ".join(n["loja"] for n in novidades))
        enviados = 0
        desde = self.agora - RESFRIAMENTO
        for insc in p.get("inscricoes") or []:
            if not insc.get("ativo", True):
                continue
            achados = [n for n in novidades if not self.db.avisado_recentemente(insc["id"], n["loja"], desde)]
            if not achados:
                continue
            for linha in self.notif.avisar(p, insc, achados):
                linha["enviado_em"] = self.agora.isoformat()
                self.db.registrar_aviso(linha)
            enviados += 1
        self.notif.avisar_admin(p, novidades)
        return enviados

    def _salvar_lojas(self, modo: str):
        linhas = []
        if modo in ("rapido", "tudo"):
            for l in self.lojas:
                linhas.append({"nome": l["nome"], "dominio": l.get("dominio"),
                               "tipo": self._tipo_detectado.get(l["nome"], l.get("tipo")),
                               "frequencia": "a cada 5 min", "ok": self._status_loja.get(l["nome"]),
                               "atualizado_em": self.agora.isoformat()})
        if modo in ("feeds", "tudo") and getattr(self, "_feed_cache", None):
            from .feeds import DOMINIOS
            for loja in self._feed_cache:
                linhas.append({"nome": loja, "dominio": DOMINIOS.get(loja), "tipo": "feed afiliado",
                               "frequencia": "a cada hora", "ok": True, "atualizado_em": self.agora.isoformat()})
        if modo in ("tiktok", "tudo"):
            linhas.append({"nome": "TikTok Shop", "dominio": "shop.tiktok.com", "tipo": "link",
                           "frequencia": "2x por dia", "ok": self._status_loja.get("TikTok Shop"),
                           "atualizado_em": self.agora.isoformat()})
        try:
            self.db.salvar_lojas(linhas)
        except Exception as e:  # noqa: BLE001
            log.warning("Não salvei a lista de lojas: %s", e)
