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
        pagina.locator("#q").fill("Inexistente")
        pagina.locator("#sugestoes .ver-todos").click()
        pagina.locator("#pedirBuscaAtual").click()
        assert pagina.locator("#nome").input_value().lower() == "inexistente"
        assert not erros
        browser.close()
