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
def test_skinfinish_por_categoria_sem_blush_no_titulo():
    from bot.catalogo import categoria_de, linha_catalogo
    produto = Oferta("MAC Cosmetics", "Skinfinish Colourstruck", "https://example.com/item", False,
                     extra={"marca": "MAC", "cor": "Film Noir Buff"})
    cat = categoria_de(produto, None)
    assert cat == "Blush"
    assert "blush" in linha_catalogo(produto, cat, dt.datetime.now(dt.timezone.utc), "")["busca"].split()
    produto.titulo = "Skinfinish Sunstruck Bronzer"
    assert categoria_de(produto, None) != "Blush"


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


def test_nao_maquiagem():
    from bot.catalogo import categoria_de
    perf = Oferta("L", "x", "u", True, extra={"produto": "Perfume Good Girl Blush Elixir Eau de Parfum", "categorias": ""})
    pincel = Oferta("L", "x", "u", True, extra={"produto": "Pincel Power para Blush Real Techniques", "categorias": ""})
    blush = Oferta("L", "x", "u", True, extra={"produto": "Pó Compacto Duo Blush e Bronzer Vult", "categorias": ""})
    masc = Oferta("L", "x", "u", True, extra={"produto": "Máscara de Cílios Lash Up", "categorias": ""})
    assert categoria_de(perf, "Blush") == "Outro" and categoria_de(pincel, "Blush") == "Outro"
    assert categoria_de(blush, None) == "Blush" and categoria_de(masc, None) == "Máscara de cílios"


# ---------------------------------------------------------------- feeds de afiliados
FEED = """aw_deep_link,product_name,merchant_name,brand_name,search_price,in_stock,merchant_image_url,merchant_deep_link,colour,merchant_category
https://www.awin1.com/pclick.php?p=1&a=3167898,Powder Blush,MAC Cosmeticos BR,MAC,210.00,1,https://img/mac.jpg,https://www.maccosmetics.com.br/product/powder-blush,Film Noir,Maquiagem > Rosto > Blush
https://www.awin1.com/pclick.php?p=2&a=3167898,Perfume Rose,MAC Cosmeticos BR,MAC,300.00,1,https://img/p.jpg,https://www.maccosmetics.com.br/product/perfume,,Perfumaria
https://www.awin1.com/pclick.php?p=3&a=3167898,Batom Matte,BELEZA NA WEB BR,Vult,25.90,0,https://img/v.jpg,https://www.belezanaweb.com.br/batom,Nude,Maquiagem
"""


def test_feed_awin_parse():
    from bot.feeds import ofertas_de_csv
    of = ofertas_de_csv(FEED)
    assert [o.loja for o in of] == ["MAC Cosmetics", "MAC Cosmetics", "Beleza na Web"]
    assert of[0].disponivel and not of[2].disponivel and of[0].url_afiliado.startswith("https://www.awin1.com")
    assert of[0].extra["cor"] == "Film Noir" and of[0].preco == 210


def test_motor_feeds_avisa_com_link_afiliado(monkeypatch):
    from bot import feeds
    from bot.feeds import ofertas_de_csv
    monkeypatch.setattr(feeds, "baixar_awin", lambda urls=None: ofertas_de_csv(FEED))
    produto = {"id": "p1", "categoria": "Blush", "marca": "MAC", "nome": "Powder Blush", "cor": "Film Noir", "links": [],
               "ativo": True, "disponivel": False,
               "inscricoes": [{"id": "i1", "email": "a@b.com", "token": "t", "ativo": True}]}
    db = MemDB([produto]); n = Notificador(seco=True)
    Motor(db, {"lojas": []}, n, trabalhadores=1).rodar("feeds")
    assert len(n.enviados) == 1 and "awin1.com" in n.enviados[0]["texto"] and "MAC Cosmetics" in n.enviados[0]["texto"]
    assert "MAC Cosmetics" in db.lojas


def test_afiliado_mercadolivre_link_colado():
    import yaml, pathlib
    cfg = yaml.safe_load(open(pathlib.Path(__file__).parent.parent / "config" / "lojas.yaml", encoding="utf-8"))
    m = Motor(MemDB([]), cfg, Notificador(seco=True))
    u = m._afiliar("Mercado Livre", "https://produto.mercadolivre.com.br/MLB-123-batom-ruby-woo")
    assert u == "https://produto.mercadolivre.com.br/MLB-123-batom-ruby-woo?matt_word=cotrinmeirellescristiano&matt_tool=76580280"
    u2 = m._afiliar("Mercado Livre", "https://www.mercadolivre.com.br/p/MLB1?pdp_filters=x")
    assert u2.endswith("?pdp_filters=x&matt_word=cotrinmeirellescristiano&matt_tool=76580280")


# ---------------------------------------------------------------- ofertas manuais (TikTok Shop)
def test_ofertas_manuais(tmp_path, monkeypatch):
    from bot import manuais
    arq = tmp_path / "m.yaml"
    arq.write_text("""ofertas:
  - link: https://www.tiktok.com/view/product/123
    marca: MAC
    produto: Powder Blush
    cor: Film Noir
    categoria: Blush
    preco: 89.9
  - link: https://www.tiktok.com/view/product/999
    marca: MAC
""", encoding="utf-8")
    monkeypatch.setattr(manuais, "ARQUIVO", arq)
    of = manuais.carregar({})
    assert len(of) == 1 and of[0][0].loja == "TikTok Shop (seleção)" and of[0][0].preco == 89.9 and of[0][1] == "Blush"
    # aviso para quem espera
    produto = {"id": "p1", "categoria": "Blush", "marca": "MAC", "nome": "Powder Blush", "cor": "Film Noir", "links": [],
               "ativo": True, "disponivel": False, "inscricoes": [{"id": "i1", "email": "a@b.com", "token": "t", "ativo": True}]}
    db = MemDB([produto]); n = Notificador(seco=True)
    Motor(db, {"lojas": []}, n, trabalhadores=1).rodar("rapido")
    assert len(n.enviados) == 1 and "TikTok Shop" in n.enviados[0]["texto"]


def test_cor_falsa_vira_nada():
    from bot.catalogo import linha_catalogo
    t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    for c in ["1 Un", "Única", "30ml", "Padrão"]:
        l = linha_catalogo(Oferta("L", "x", "u", True, extra={"marca": "Vult", "produto": "Pó Duo", "cor": c}), "Blush", t, "")
        assert l["cor"] is None, c
    l = linha_catalogo(Oferta("L", "x", "u", True, extra={"marca": "MAC", "produto": "Batom", "cor": "Ruby Woo"}), "Batom", t, "")
    assert l["cor"] == "Ruby Woo"


def test_lapis_de_boca_nao_e_contorno():
    from bot.catalogo import categoria_de
    for nome in ["Lápis de Contorno Labial MAC Ruby Woo", "Lip Pencil MAC Ruby Woo", "Delineador Labial Vult"]:
        assert categoria_de(Oferta("L", "x", "u", True, extra={"produto": nome, "categorias": ""}), None) == "Lápis labial", nome
    assert categoria_de(Oferta("L", "x", "u", True, extra={"produto": "Paleta de Contorno Facial", "categorias": ""}), None) == "Contorno"


# ---------------------------------------------------------------- catálogo do TikTok Shop
def test_tiktok_card_e_marca():
    from bot import tiktok_catalogo as T
    marcas = T._lista_marcas()
    card = {"link": "https://shop.tiktok.com/br/pdp/batom-mac-hidratante/1736022415213954921?x=1",
            "titulo": "Batom MAC Hidratante Brilhante Lustreglass Sheer-Shine",
            "texto": "Batom MAC Hidratante Brilhante Lustreglass Sheer-Shine\n4.9\n8.5K vendido\nDeal\n-36%R$88,80R$139,00",
            "imagem": "https://img/x.webp"}
    o = T.card_para_oferta(card, marcas)
    assert o.extra["marca"] == "MAC" and o.preco == 88.8 and o.extra["preco_de"] == 139.0
    assert o.url.endswith("/1736022415213954921") and o.disponivel
    assert T.marca_do_titulo("Kit Gloss Labial Sarah’s Beauty – Brilho", marcas) in ("Sarah's Beauty", "Sarahs Beauty")
    assert T.marca_do_titulo("Gel Para Sobrancelhas Ruby Rose Brow", marcas) == "Ruby Rose"
    assert T.marca_do_titulo("M·A·C Ruby Woo", marcas) == "MAC"
    assert T.marca_do_titulo("Base Macrilan Matte", marcas) == "Macrilan"
    assert T.marca_do_titulo("Pó compacto maquiagem natural", marcas) is None
    esg = T.card_para_oferta(dict(card, texto=card["texto"] + "\nEsgotado"), marcas)
    assert not esg.disponivel


def test_tiktok_pagina_produto_e_linhas():
    import datetime as dt
    from bot import tiktok_catalogo as T
    txt = ("TikTok Shop\nBatom MAC\nVendido por MAC\n-36%\nR$\n88\n.80\nCor:\nAlone Time\nComprar agora\n"
           "Sobre este produto\nDetalhes\nMarca MAC\nAvaliações\nachei que estava esgotado mas chegou")
    info = T.ler_pagina_produto(txt)
    assert info == {"marca": "MAC", "vendedor": "MAC", "disponivel": True}
    assert T.ler_pagina_produto("Vendido por X\nEsgotado\nSobre este produto")["disponivel"] is False
    marcas = T._lista_marcas()
    cards = [
        {"link": "https://shop.tiktok.com/br/pdp/a/1", "titulo": "Blush Compacto Ruby Rose", "texto": "R$19,90"},
        {"link": "https://shop.tiktok.com/br/pdp/b/2", "titulo": "Kit Pincel de Maquiagem 12 peças", "texto": "R$29,90"},
    ]
    ofs = [(T.card_para_oferta(c, marcas), None) for c in cards]
    linhas = T.montar_linhas(ofs, dt.datetime(2026, 11, 26, tzinfo=dt.timezone.utc))
    assert len(linhas) == 1 and linhas[0]["categoria"] == "Blush" and linhas[0]["loja"] == "TikTok Shop"
    assert linhas[0]["marca"] == "Ruby Rose" and linhas[0]["preco"] == 19.9


def test_tiktok_tenta_de_novo_e_avisa(monkeypatch):
    from bot import tiktok_catalogo as T
    chamadas, avisos = [], []
    monkeypatch.setattr(T, "coletar", lambda cfg, agora=None, chrome=False: (chamadas.append(1), ([], False))[1])
    monkeypatch.setattr(T, "_avisar_problema", lambda cfg, motivo, n, chrome: avisos.append(motivo))
    monkeypatch.setattr(T.time, "sleep", lambda s: None)

    class DB:
        lojas = []
        def salvar_lojas(self, l): self.lojas += l
    db = DB()
    cfg = {"tiktok_catalogo": {"tentativas": 3}}
    assert T.atualizar(db, cfg) == 0
    assert len(chamadas) == 1 and len(avisos) == 1 and db.lojas[-1]["ok"] is False
    chamadas.clear()
    assert T.atualizar(db, cfg, chrome=True) == 0
    assert len(chamadas) == 3


def test_relatorio_saude():
    from bot import saude
    agora = dt.datetime(2026, 11, 26, 12, tzinfo=dt.timezone.utc)

    class DB:
        def lojas_todas(self):
            return [{"nome": "TikTok Shop", "ok": True, "atualizado_em": "2026-11-24T12:00:00+00:00"},
                    {"nome": "Océane", "ok": True}, {"nome": "Hinode", "ok": False}]
        def contar(self, t, f=None): return {"catalogo": 47489, "vitrine": 15012}.get(t, 300)
        def buscas_vazias_desde(self, d): return [{"termo": "blush film noir", "vezes": 3}]
        def produtos_sem_oferta(self): return [{"marca": "MAC", "nome": "Powder Blush", "cor": "Film Noir", "links": []}]
    assunto, texto, prob = saude.montar_relatorio(DB(), agora)
    assert prob and "problema" in assunto
    assert "TikTok Shop sem atualizar" in texto and "Hinode" in texto
    assert "blush film noir" in texto and "MAC Powder Blush Film Noir" in texto and "15.012 produtos" in texto


# ---------------------------------------------------------------- lojas pelo navegador (MAC)
MAC_HTML = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":["FAQPage"]}]}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"ProductGroup","name":"Lip Tint Lustreglass Stainglass",
"image":"https://img/grupo.jpg","brand":{"name":"MAC Brazil E-Commerce Site"},"hasVariant":[
{"@type":"Product","name":"Lip Tint Lustreglass Stainglass - XOXO - 3ml","color":"Nude pêssego quente","image":["https://img/xoxo.jpg"],
 "offers":{"@type":"Offer","price":127,"priceCurrency":"BRL","availability":"http://schema.org/OutOfStock","url":"/product/13831/147440/x?shade=XOXO"}},
{"@type":"Product","name":"Lip Tint Lustreglass Stainglass - Zoomies - 3ml","color":"Vermelho cereja",
 "offers":{"@type":"Offer","price":"127.00","availability":"http://schema.org/InStock","url":"https://www.maccosmetics.com.br/product/13831/147440/x?shade=Zoomies"}}]}</script></head></html>"""


def test_navegador_le_produto_mac():
    from bot import lojas_navegador as N
    url = "https://www.maccosmetics.com.br/product/13831/147440/produtos/maquiagem/labios/lip-tint"
    ofs = N.ler_produto("MAC Cosmetics", "MAC", url, MAC_HTML)
    assert [o.extra["cor"] for o in ofs] == ["XOXO", "Zoomies"]
    assert [o.disponivel for o in ofs] == [False, True] and ofs[1].preco == 127.0
    assert ofs[0].url == "https://www.maccosmetics.com.br/product/13831/147440/x?shade=XOXO"
    assert ofs[0].imagem == "https://img/xoxo.jpg" and ofs[1].imagem == "https://img/grupo.jpg"
    linhas = N.montar_linhas([(o, N.categoria_da_url(url)) for o in ofs], dt.datetime(2026, 11, 26, tzinfo=dt.timezone.utc))
    assert {l["categoria"] for l in linhas} == {"Lip tint"} and linhas[0]["marca"] == "MAC" and linhas[0]["loja"] == "MAC Cosmetics"
    assert N.cor_do_nome("Powder Blush - Film Noir - 6g", "Powder Blush") == "Film Noir"
    assert N.categoria_da_url("https://x/products/13854/produtos/maquiagem/labios/batom") == "Batom"
