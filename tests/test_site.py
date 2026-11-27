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
