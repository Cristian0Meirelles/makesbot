from unittest.mock import MagicMock

import pytest

from bot import lojas, lojas_navegador, main


def test_navegador_sem_pc(monkeypatch):
    chamada = MagicMock(return_value=2)
    monkeypatch.setattr(lojas_navegador, "atualizar", chamada)
    assert main.main(["navegador", "--seco"]) == 0
    assert chamada.call_args.kwargs == {"chrome": False, "so_loja": None, "seco": True}


def test_configuracao_ausente_falha(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert main.main(["navegador"]) == 2


def test_redirecionamento_fora_da_lista(monkeypatch):
    sessao = MagicMock()
    resposta = sessao.get.return_value.__enter__.return_value
    resposta.is_redirect = True
    resposta.headers = {"Location": "https://pendente.example/produto"}
    monkeypatch.setattr(lojas, "sessao", lambda: sessao)
    with pytest.raises(lojas.LojaBloqueada):
        lojas.verificar_link("Sephora", "https://www.sephora.com.br/maquiagem")
    assert sessao.get.call_count == 1
    assert sessao.get.call_args.kwargs["allow_redirects"] is False


def test_estoque_ausente_nao_e_esgotado():
    html = '<script type="application/ld+json">{"@type":"Product","name":"Batom","offers":{"price":99}}</script>'
    assert lojas.ofertas_de_pagina("Loja", "https://loja.example/p", html) == []
    assert lojas_navegador.ler_produto("MAC Cosmetics", "MAC", "https://www.maccosmetics.com.br/p", html) == []
