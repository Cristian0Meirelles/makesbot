"""Acesso ao banco. SupabaseDB fala com a API REST do Supabase; MemDB é para testes."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from urllib.parse import quote

import requests


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat()


class SupabaseDB:
    def __init__(self, url: str, chave_service: str):
        self.base = url.rstrip("/") + "/rest/v1"
        self.s = requests.Session()
        self.s.headers.update({
            "apikey": chave_service,
            "Authorization": f"Bearer {chave_service}",
            "Content-Type": "application/json",
        })

    def _req(self, metodo, caminho, **kw):
        r = self.s.request(metodo, f"{self.base}/{caminho}", timeout=30, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {metodo} {caminho}: {r.status_code} {r.text[:300]}")
        return r.json() if r.text else None

    # ---- leitura -----------------------------------------------------
    def alvos(self) -> list[dict]:
        dados = self._req("GET", "produtos", params={
            "select": "*,inscricoes(id,nome,email,whatsapp,callmebot_key,token,ativo)",
            "ativo": "eq.true",
            "inscricoes.ativo": "eq.true",
        })
        return [p for p in dados if p.get("inscricoes")]

    def ofertas_por_produto(self, ids: list[str]) -> dict[str, list[dict]]:
        saida: dict[str, list[dict]] = defaultdict(list)
        for i in range(0, len(ids), 80):
            lote = ",".join(ids[i:i + 80])
            for o in self._req("GET", "ofertas", params={"produto_id": f"in.({lote})", "select": "*"}) or []:
                saida[o["produto_id"]].append(o)
        return saida

    def avisado_recentemente(self, inscricao_id: str, loja: str, desde: dt.datetime) -> bool:
        r = self._req("GET", "avisos", params={
            "inscricao_id": f"eq.{inscricao_id}", "loja": f"eq.{loja}",
            "enviado_em": f"gte.{_iso(desde)}", "ok": "is.true", "select": "id", "limit": "1",
        })
        return bool(r)

    # ---- escrita -----------------------------------------------------
    def substituir_ofertas(self, produto_id: str, loja: str, ofertas: list[dict]):
        self._req("DELETE", f"ofertas?produto_id=eq.{produto_id}&loja=eq.{quote(loja)}")
        if ofertas:
            self._req("POST", "ofertas", json=ofertas, headers={"Prefer": "return=minimal"})

    def atualizar_produto(self, produto_id: str, campos: dict):
        self._req("PATCH", f"produtos?id=eq.{produto_id}", json=campos, headers={"Prefer": "return=minimal"})

    def registrar_aviso(self, linha: dict):
        self._req("POST", "avisos", json=linha, headers={"Prefer": "return=minimal"})

    def salvar_lojas(self, linhas: list[dict]):
        if linhas:
            self._req("POST", "lojas", json=linhas,
                      headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def salvar_catalogo(self, linhas: list[dict]):
        for i in range(0, len(linhas), 500):
            self._req("POST", "catalogo?on_conflict=loja,url", json=linhas[i:i + 500],
                      headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def limpar_catalogo(self, antes: dt.datetime):
        self._req("DELETE", f"catalogo?atualizado_em=lt.{quote(_iso(antes))}")


class MemDB:
    """Banco em memória, usado nos testes e no modo --seco sem Supabase."""

    def __init__(self, produtos: list[dict] | None = None):
        self.produtos = {p["id"]: p for p in (produtos or [])}
        self.ofertas: list[dict] = []
        self.avisos: list[dict] = []
        self.lojas: dict[str, dict] = {}

    def alvos(self):
        return [p for p in self.produtos.values()
                if p.get("ativo", True) and [i for i in p.get("inscricoes", []) if i.get("ativo", True)]]

    def ofertas_por_produto(self, ids):
        saida = defaultdict(list)
        for o in self.ofertas:
            if o["produto_id"] in ids:
                saida[o["produto_id"]].append(o)
        return saida

    def avisado_recentemente(self, inscricao_id, loja, desde):
        return any(a["inscricao_id"] == inscricao_id and a["loja"] == loja and a["ok"]
                   and a["enviado_em"] >= desde for a in self.avisos)

    def substituir_ofertas(self, produto_id, loja, ofertas):
        self.ofertas = [o for o in self.ofertas if not (o["produto_id"] == produto_id and o["loja"] == loja)]
        self.ofertas.extend(ofertas)

    def atualizar_produto(self, produto_id, campos):
        self.produtos[produto_id].update(campos)

    def registrar_aviso(self, linha):
        linha = dict(linha)
        linha["enviado_em"] = linha.get("enviado_em") or dt.datetime.now(dt.timezone.utc)
        if isinstance(linha["enviado_em"], str):
            linha["enviado_em"] = dt.datetime.fromisoformat(linha["enviado_em"])
        self.avisos.append(linha)

    def salvar_lojas(self, linhas):
        for l in linhas:
            self.lojas[l["nome"]] = l
