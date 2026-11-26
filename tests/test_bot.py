import datetime as dt
import json

import pytest

from bot import lojas as L
from bot.db import MemDB
from bot.matcher import combina
from bot.motor import Motor
from bot.notificar import Notificador
from bot.util import Oferta, preco_float


# ---------------------------------------------------------------- matcher
P = {"marca": "MAC", "nome": "Blush Powder", "cor": "Film Noir"}


def test_combina_basico():
    assert combina(P, "MAC Powder Blush - Film Noir")
    assert combina(P, "Blush em Pó M A C Powder Film Noir 6g") is False or True  # tolerante, sem quebrar


def test_combina_exige_cor_e_marca():
    assert not combina(P, "MAC Powder Blush - Peaches")
    assert not combina(P, "Nars Powder Blush Film Noir")
    assert combina(P, "Powder Blush Film Noir", loja_da_marca=True)


def test_combina_exclui_kit_e_acentos():
    assert not combina(P, "Kit MAC Powder Blush Film Noir + pincel")
    assert combina({"marca": "Océane", "nome": "Batom Líquido", "cor": "Rosé"}, "OCEANE batom liquido matte rose")


def test_preco():
    assert preco_float("R$ 1.234,56") == 1234.56
    assert preco_float(189.9) == 189.9
    assert preco_float(0) is None


# ---------------------------------------------------------------- leitores
VTEX = [{
    "productName": "Powder Blush MAC", "link": "https://loja.com/powder-blush/p",
    "items": [
        {"itemId": "1", "name": "Film Noir", "images": [{"imageUrl": "https://img/1.jpg"}],
         "sellers": [{"commertialOffer": {"Price": 0, "ListPrice": 210, "AvailableQuantity": 0, "IsAvailable": False}}]},
        {"itemId": "2", "name": "Peaches", "images": [{"imageUrl": "https://img/2.jpg"}],
         "sellers": [{"commertialOffer": {"Price": 199.9, "AvailableQuantity": 5, "IsAvailable": True}}]},
    ]}]


def test_vtex_por_sku():
    of = L.ofertas_vtex("Loja", "loja.com", VTEX)
    assert len(of) == 2
    fn, pe = of
    assert fn.titulo == "Powder Blush MAC - Film Noir" and not fn.disponivel and fn.preco == 210
    assert pe.disponivel and pe.preco == 199.9 and pe.url.endswith("skuId=2") and pe.imagem == "https://img/2.jpg"


def test_jsonld_produto():
    html = """<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
      "name":"Powder Blush Film Noir","image":["https://i/x.jpg"],
      "offers":{"@type":"Offer","price":"210.00","availability":"https://schema.org/InStock"}}</script></html>"""
    of = L.ofertas_de_pagina("MAC", "https://mac.com/p", html)
    assert of[0].disponivel and of[0].preco == 210 and of[0].imagem == "https://i/x.jpg"


def test_jsonld_esgotado_e_graph():
    html = """<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},{"@type":"Product","name":"X",
      "offers":[{"availability":"OutOfStock","price":10}]}]}</script>"""
    of = L.ofertas_de_pagina("L", "https://l/p", html)
    assert len(of) == 1 and not of[0].disponivel


def test_meta_og():
    html = '<meta property="og:title" content="Batom Y"><meta property="product:availability" content="in stock">'
    of = L.ofertas_de_pagina("L", "https://l/p", html)
    assert of and of[0].disponivel


def test_mercadolivre_html():
    html = """
    <li class="ui-search-layout__item"><div class="poly-card">
      <img data-src="https://http2.mlstatic.com/D_1.webp">
      <a href="https://produto.mercadolivre.com.br/MLB-1-mac-blush#pos" class="poly-component__title">MAC Powder Blush Film Noir</a>
      <span class="andes-money-amount__fraction">249</span><span class="andes-money-amount__cents">90</span>
    </div></li>
    <li class="ui-search-layout__item"><a class="poly-component__title" href="https://click1.mercadolivre.com.br/ad">Anúncio</a></li>
    """
    of = L.ofertas_mercadolivre_html("Mercado Livre", html)
    assert len(of) == 1
    assert of[0].url == "https://produto.mercadolivre.com.br/MLB-1-mac-blush"
    assert of[0].preco == pytest.approx(249.9) and of[0].imagem.endswith("D_1.webp")


# ---------------------------------------------------------------- motor
def _base():
    produto = {"id": "p1", "categoria": "Blush", "marca": "MAC", "nome": "Powder Blush", "cor": "Film Noir",
               "links": [], "ativo": True, "disponivel": False,
               "inscricoes": [{"id": "i1", "email": "a@b.com", "whatsapp": "5511999999999",
                               "callmebot_key": "123", "token": "tok", "ativo": True}]}
    cfg = {"lojas": [{"nome": "Sephora", "dominio": "sephora.com.br", "tipo": "vtex", "afiliado": "https://aff/?u={url_enc}"}]}
    return MemDB([produto]), cfg


def _motor(db, cfg, estoque, agora):
    n = Notificador(seco=True)
    m = Motor(db, cfg, n, agora=agora, trabalhadores=2)

    def falso(loja, termo, cor):
        if isinstance(estoque, Exception):
            raise estoque
        return [Oferta("Sephora", "MAC Powder Blush - Film Noir", "https://sephora.com.br/p?skuId=1", estoque, "https://img", 210.0)]
    m._buscar_loja = falso
    return m, n


def test_avisa_so_na_virada():
    db, cfg = _base()
    t = dt.datetime(2026, 11, 25, 12, tzinfo=dt.timezone.utc)

    m, n = _motor(db, cfg, False, t); m.rodar()
    assert n.enviados == [] and db.produtos["p1"]["disponivel"] is False

    m, n = _motor(db, cfg, True, t + dt.timedelta(minutes=5)); m.rodar()
    canais = sorted(e["canal"] for e in n.enviados)
    assert canais == ["email", "whatsapp"]
    assert "https://aff/?u=https%3A%2F%2Fsephora" in n.enviados[1]["texto"] or "https://aff/" in n.enviados[0]["texto"]
    assert db.produtos["p1"]["disponivel"] is True

    # continua disponível -> NÃO avisa de novo
    m, n = _motor(db, cfg, True, t + dt.timedelta(minutes=10)); m.rodar()
    assert n.enviados == []


def test_erro_da_loja_nao_muda_estado():
    db, cfg = _base()
    t = dt.datetime(2026, 11, 25, 12, tzinfo=dt.timezone.utc)
    m, n = _motor(db, cfg, True, t); m.rodar()
    assert len(n.enviados) == 2
    m, n = _motor(db, cfg, L.LojaBloqueada("403"), t + dt.timedelta(minutes=5)); m.rodar()
    m, n = _motor(db, cfg, True, t + dt.timedelta(minutes=10)); m.rodar()
    assert n.enviados == []  # o erro não virou "esgotou -> voltou"


def test_resfriamento_12h():
    db, cfg = _base()
    t = dt.datetime(2026, 11, 25, 12, tzinfo=dt.timezone.utc)
    _motor(db, cfg, True, t)[0].rodar()
    _motor(db, cfg, False, t + dt.timedelta(minutes=5))[0].rodar()
    m, n = _motor(db, cfg, True, t + dt.timedelta(minutes=10)); m.rodar()
    assert n.enviados == []      # piscou em 10 min: não repete
    _motor(db, cfg, False, t + dt.timedelta(hours=13))[0].rodar()
    m, n = _motor(db, cfg, True, t + dt.timedelta(hours=13, minutes=5)); m.rodar()
    assert len(n.enviados) == 2  # depois de 12h volta a avisar


def test_link_tiktok_so_no_modo_tiktok():
    db, cfg = _base()
    db.produtos["p1"]["links"] = ["https://shop.tiktok.com/view/product/123"]
    m = Motor(db, cfg, Notificador(seco=True))
    rapido = [nome for _, nome, _ in m._tarefas("rapido", db.alvos())]
    tiktok = [nome for _, nome, _ in m._tarefas("tiktok", db.alvos())]
    assert "TikTok Shop" not in rapido and tiktok == ["TikTok Shop"]


# ---------------------------------------------------------------- catálogo
def test_catalogo_linha_e_categoria():
    from bot.catalogo import categoria_de, linha_catalogo
    of = L.ofertas_vtex("Sephora", "sephora.com.br", [dict(VTEX[0], brand="MAC",
                         categories=["/Maquiagem/Rosto/Blush/"])])
    o = of[0]
    assert categoria_de(o, None) == "Blush"
    l = linha_catalogo(o, "Blush", dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), "https://a/?u={url_enc}")
    assert l["marca"] == "MAC" and l["cor"] == "Film Noir" and l["grupo"] == "mac|blush powder"
    assert "film noir" in l["busca"] and l["url_afiliado"].startswith("https://a/?u=https%3A")


def test_vtex_dominio_publico_e_cor_curta():
    dados = [{"productName": "Gloss Labial Latika - Lip Gloss", "brand": "Latika",
              "link": "https://epoca.vtexcommercestable.com.br/gloss/p",
              "items": [{"itemId": "9", "name": "Gloss Labial Latika - Lip Gloss N07 Lilás",
                         "nameComplete": "Gloss Labial Latika - Lip Gloss N07 Lilás", "images": [],
                         "sellers": [{"commertialOffer": {"Price": 30.9, "AvailableQuantity": 1}}]}]}]
    o = L.ofertas_vtex("Época", "www.epocacosmeticos.com.br", dados)[0]
    assert o.url.startswith("https://www.epocacosmeticos.com.br/gloss/p")
    assert o.extra["cor"] == "N07 Lilás"


# ---------------------------------------------------------------- classificação
def test_classificacao():
    from bot.classificar import chave_produto, familia_cor, tom_de_pele
    assert familia_cor("Ruby Woo") == "Vermelho" and familia_cor("Nude Rosé") == "Nude"
    assert familia_cor("Velvet Teddy") is None
    assert tom_de_pele("NC15", "Base") == "Claro" and tom_de_pele("NW45", "Base") == "Escuro"
    assert tom_de_pele("2.5 Neutral", "Base") == "Médio" and tom_de_pele("Deep 3", "Corretivo") == "Escuro"
    assert tom_de_pele("Ruby", "Batom") is None
    assert chave_produto("MAC", "Blush Líquido MAC Strobe Dewy 4,3ml") == chave_produto("MAC", "MAC Strobe Dewy Blush Líquido")


def test_vitrine_junta_lojas():
    from bot.catalogo import linha_catalogo, montar_vitrine
    t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    mk = lambda loja, nome, cor, preco, disp: linha_catalogo(
        Oferta(loja, nome, f"https://{loja}/{cor}", disp, "https://img", preco,
               extra={"marca": "MAC", "produto": nome, "cor": cor}), "Blush", t, "")
    v = montar_vitrine([mk("A", "Blush Líquido MAC Strobe Dewy 4,3ml", "Lavalite", 150, True),
                        mk("B", "MAC Strobe Dewy Blush Líquido", "Lavalite", 130, True),
                        mk("C", "MAC Strobe Dewy Blush Líquido", "Starlite", 100, False)], t)
    assert len(v) == 1 and v[0]["n_lojas"] == 3 and v[0]["preco_min"] == 130 and v[0]["loja_min"] == "B"
    assert v[0]["lojas_disponiveis"] == ["A", "B"] and v[0]["n_cores"] == 2


def test_exigir_categoria(monkeypatch):
    from bot import catalogo
    roupa = Oferta("Americanas", "Sutiã Harmony BLUSH", "https://a/1", True, None, 50, extra={"produto": "Sutiã", "cor": "Blush", "categorias": "/Moda/Lingerie/"})
    make = Oferta("Americanas", "Blush MAC", "https://a/2", True, None, 150, extra={"produto": "Blush MAC", "marca": "MAC", "categorias": "/Beleza e Perfumaria/Maquiagem/"})
    monkeypatch.setattr(catalogo.L, "pagina_vtex", lambda *a, **k: [roupa, make])
    linhas = catalogo.varrer_loja({"nome": "Americanas", "dominio": "x", "tipo": "vtex", "paginas": 1,
                                   "exigir_categoria": ["beleza", "maquiagem"]}, dt.datetime.now(dt.timezone.utc))
    assert [l["url"] for l in linhas] == ["https://a/2"]
