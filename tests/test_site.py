"""Executar com pytest e Chromium do requirements-browser.txt."""
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
DOCS = Path(__file__).resolve().parents[1] / "docs"


@pytest.mark.parametrize("largura", [390, 1280])
def test_busca_paginada_e_detalhe(largura):
    amostra = [{"grupo": str(i), "marca": "MAC", "produto": f"Blush {i}", "loja": "MAC",
                "categoria": "Blush", "titulo": f"Blush {i}", "url": "https://example.com/p",
                "preco": 20, "disponivel": False, "busca": "mac blush"} for i in range(501)]
    amostra.append(dict(amostra[0], grupo="outro", marca="Macrilan", busca="macrilan blush"))
    for cor, preco, disponivel in [("Myth", 100.74, True), ("Film Noir", 150, False)]:
        amostra.append(dict(amostra[0], grupo="batom", produto="MACximal", categoria="Batom",
                            titulo="MACximal " + cor, cor=cor, preco=preco, disponivel=disponivel,
                            busca="mac batom macximal " + cor.lower()))
    amostra.append(dict(amostra[-2], loja="Loja com outra cor", disponivel=False))
    amostra.append(dict(amostra[-1], loja="Loja sem cor", cor=None, busca="mac batom macximal"))
    with pw.sync_playwright() as driver:
        browser = driver.chromium.launch()
        pagina = browser.new_page(viewport={"width": largura, "height": 800})
        erros = []
        pagina.on("pageerror", lambda erro: erros.append(str(erro)))

        def recurso(route):
            base = "https://voltou.test/"
            url = route.request.url
            if not url.startswith(base):
                return route.abort()
            arquivo = url[len(base):] or "index.html"
            if arquivo == "demo.json":
                return route.fulfill(json={"lojas": [], "catalogo": amostra})
            if arquivo == "config.js":
                return route.fulfill(content_type="application/javascript", body="window.VOLTOU_CONFIG={};")
            caminho = DOCS / arquivo
            if caminho.is_file():
                return route.fulfill(path=caminho)
            route.fulfill(status=404)

        pagina.route("**/*", recurso)
        pagina.goto("https://voltou.test/")
        pagina.locator("#gradeCat .card").first.wait_for()
        pagina.locator("#q").fill("blu")
        primeira = pagina.locator("#sugestoes .sug").first
        pw.expect(primeira).to_be_visible()
        assert pagina.locator("#q").input_value() == "blu"
        primeira.click()
        pw.expect(pagina.locator("#produtoCorpo")).to_contain_text("Blush")
        pagina.locator("#fecharProduto").click()
        pagina.locator("#btnBuscar").click()
        pw.expect(pagina.locator("#catInfo")).to_contain_text("502 produtos")
        assert pagina.locator("#fBusca").input_value() == "blu"
        pagina.locator("#q").fill("blush MAC")
        pw.expect(pagina.locator("#sugestoes .sug")).to_have_count(6)
        pagina.locator("#q").press("Enter")
        pw.expect(pagina.locator("#sugestoes")).to_be_hidden()
        pw.expect(pagina.locator("#catInfo")).to_contain_text("501 produtos")
        assert pagina.locator("#q").input_value() == "blush MAC"
        assert not pagina.locator("#modalProduto").is_visible()
        pagina.get_by_role("button", name="Próxima página").click()
        pagina.locator("#gradeCat .card").first.click()
        pw.expect(pagina.locator("#produtoCorpo")).to_contain_text("Blush")
        pagina.locator("#fecharProduto").click()
        pagina.locator("#q").fill("film noir")
        pagina.locator("#q").press("Enter")
        batom = pagina.locator("#gradeCat .card").filter(has_text="MACximal")
        pw.expect(batom).to_contain_text("Esgotado")
        pw.expect(batom).to_contain_text("150,00")
        batom.click()
        pw.expect(pagina.locator("#produtoCorpo .resumo")).to_contain_text("Film Noir")
        pw.expect(pagina.locator("#produtoCorpo .linha-loja")).to_have_count(3)
        pw.expect(pagina.locator("#produtoCorpo .linha-loja").filter(has_text="Loja com outra cor")).to_contain_text("Cor Myth")
        pw.expect(pagina.locator("#produtoCorpo .linha-loja").filter(has_text="Loja sem cor")).to_contain_text("Cor não informada")
        pw.expect(pagina.locator("#produtoCorpo .linha-loja").first).to_contain_text("esgotado")
        pagina.locator("#fecharProduto").click()
        pagina.locator("#q").fill("myth noir")
        pagina.locator("#btnBuscar").click()
        pw.expect(pagina.locator("#catInfo")).to_contain_text("Nenhum produto")
        pagina.locator("#q").fill("Inexistente")
        pagina.locator("#sugestoes .ver-todos").click()
        pagina.locator("#pedirBuscaAtual").click()
        assert pagina.locator("#nome").input_value().lower() == "inexistente"
        assert not erros
        browser.close()


def test_cadastro_exige_codigo_confirmado():
    with pw.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page()
        def recurso(route):
            url = route.request.url
            if url.startswith("https://voltou.test/"):
                nome = url.split("/")[-1]
                if nome == "config.js":
                    return route.fulfill(content_type="application/javascript", body="window.VOLTOU_CONFIG={supabaseUrl:'https://auth.supabase.co',supabaseAnonKey:'public'}")
                return route.fulfill(path=DOCS / nome)
            if "/auth/v1/signup" in url:
                return route.fulfill(json={"id": "pending"})
            if "/auth/v1/verify" in url:
                if route.request.post_data_json["token"] != "123456":
                    return route.fulfill(status=403, json={"error_code": "otp_expired"})
                return route.fulfill(json={"access_token": "verified"})
            if "/auth/v1/user" in url:
                return route.fulfill(json={"email": "cliente@example.org", "email_confirmed_at": "2026-11-26"})
            route.abort()
        page.route("**/*", recurso)
        page.goto("https://voltou.test/conta.html")
        page.locator("#alternar").click()
        page.locator("#email").fill("cliente@example.org")
        page.locator("#telefoneConta").fill("11900000000")
        for campo in ["senha", "confirmacao"]:
            page.locator("#" + campo).fill("segredo-exemplo")
        page.locator("#enviar").click()
        pw.expect(page.locator("#destino")).to_have_text("cliente@example.org")
        page.reload()
        page.locator("#codigo").fill("000000")
        page.locator("#verificacao button.primary").click()
        pw.expect(page.locator("#mensagem")).to_contain_text("Confira os dígitos")
        pw.expect(page.locator("#perfil")).to_be_hidden()
        page.locator("#codigo").fill("123456")
        page.locator("#verificacao button.primary").click()
        pw.expect(page.locator("#perfil")).to_be_visible()
        browser.close()


def test_alternativa_so_com_mesma_amostra_em_estoque():
    ref = dict(grupo="batom", categoria="Batom", loja="A", marca="MAC", produto="Batom Original",
               cor="Alone Time", disponivel=False, busca="batom original alone time", url="https://loja.test/original")
    rows = [ref, dict(ref, grupo="equivalente", produto="Outro modelo", marca="Outra marca", disponivel=True,
                      cor="Malva 12", busca="outro modelo malva", url="https://loja.test/malva"),
            dict(ref, grupo="diferente", produto="Mesmo nome de cor", disponivel=True),
            dict(ref, grupo="esgotado", produto="Outra opção esgotada")]
    paletas = {r["grupo"]: {"fonte": r["grupo"], "tons": {r["cor"].lower(): "966158" if r["grupo"] != "diferente" else "996158"}} for r in rows}
    with pw.sync_playwright() as driver:
        browser = driver.chromium.launch()
        p = browser.new_page()
        def recurso(route):
            url = route.request.url
            if not url.startswith("https://voltou.test/"):
                return route.abort()
            nome = url.removeprefix("https://voltou.test/") or "index.html"
            if nome == "config.js":
                return route.fulfill(content_type="application/javascript", body="window.VOLTOU_CONFIG={}")
            if nome == "demo.json":
                return route.fulfill(json={"catalogo": rows, "lojas": []})
            if nome == "amostras-cor.json":
                return route.fulfill(json=paletas)
            if (DOCS / nome).is_file():
                return route.fulfill(path=DOCS / nome)
            route.fulfill(status=404)
        p.route("**/*", recurso)
        p.goto("https://voltou.test/")
        p.locator("#gradeCat .card").filter(has_text="Batom Original").click()
        pw.expect(p.locator(".alternativas a")).to_have_count(1)
        pw.expect(p.locator(".alternativas")).to_contain_text("Outra marca")
        pw.expect(p.locator(".alternativas a")).to_have_attribute("href", "https://loja.test/malva")
        browser.close()


def test_tiktok_painel_precos_por_cor():
    from bot.tiktok_catalogo import ofertas_do_painel, _lista_marcas
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pagina = browser.new_page()
        pagina.set_content("""
        <section><strong id="preco">R$153,00</strong><p id="cor">Cor: Velvet Teddy</p>
        <button disabled><img alt="">Film Noir Buff</button>
        <button onclick="cor.textContent='Cor: Pony';preco.textContent='R$139,50'"><img alt="">Pony</button>
        <div>Quantidade:</div></section>""")
        itens = ofertas_do_painel(pagina, "Blush MAC Skinfinish", "https://www.tiktok.com/view/product/123", _lista_marcas())
        assert [(v.extra["cor"], v.disponivel, v.preco) for v in itens] == [
            ("Film Noir Buff", False, None), ("Pony", True, 139.5)]
        browser.close()
