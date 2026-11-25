"""Envio de avisos: e-mail (SMTP, ex.: Gmail) e WhatsApp (CallMeBot grátis ou API oficial da Meta)."""
from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import requests

from .util import brl

log = logging.getLogger("avisos")


class Notificador:
    def __init__(self, seco: bool = False):
        self.seco = seco
        self.site = os.getenv("SITE_URL", "").rstrip("/")
        # e-mail
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_porta = int(os.getenv("SMTP_PORT", "465"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_senha = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
        self.remetente = os.getenv("EMAIL_REMETENTE_NOME", "Voltou! Alertas de make")
        # WhatsApp oficial (opcional)
        self.meta_token = os.getenv("META_WA_TOKEN", "")
        self.meta_phone_id = os.getenv("META_WA_PHONE_ID", "")
        self.meta_template = os.getenv("META_WA_TEMPLATE", "")
        self.meta_lang = os.getenv("META_WA_LANG", "pt_BR")
        # cópia para o dono do site (opcional)
        self.admin_email = os.getenv("ADMIN_EMAIL", "")
        self.admin_wpp = os.getenv("ADMIN_WHATSAPP", "")
        self.admin_wpp_key = os.getenv("ADMIN_CALLMEBOT_KEY", "")
        self.enviados: list[dict] = []  # usado em testes / modo seco

    # ------------------------------------------------------------------
    def link_cancelar(self, token: str) -> str:
        return f"{self.site}/?cancelar={token}" if self.site and token else ""

    def texto_whatsapp(self, produto: dict, achados: list[dict], token: str | None) -> str:
        nome = " ".join(x for x in [produto["marca"], produto["nome"], produto.get("cor") or ""] if x).strip()
        linhas = [f"💄 *VOLTOU!* {nome}", ""]
        for a in achados:
            preco = f" por {brl(a.get('preco'))}" if a.get("preco") else ""
            linhas.append(f"🛍️ *{a['loja']}*{preco}")
            linhas.append(a.get("url_afiliado") or a["url"])
            linhas.append("")
        linhas.append("Corre que costuma acabar rápido! ⏱️")
        c = self.link_cancelar(token or "")
        if c:
            linhas.append(f"\nParar este alerta: {c}")
        return "\n".join(linhas)

    def html_email(self, produto: dict, achados: list[dict], token: str | None) -> str:
        nome = html.escape(" ".join(x for x in [produto["nome"], produto.get("cor") or ""] if x))
        marca = html.escape(produto["marca"])
        img = next((a.get("imagem") for a in achados if a.get("imagem")), None) or produto.get("imagem_loja") or produto.get("foto_url")
        img_html = (f'<img src="{html.escape(img)}" width="220" style="display:block;margin:0 auto 18px;'
                    f'border-radius:16px;max-width:100%" alt="">') if img else ""
        botoes = ""
        for a in achados:
            preco = f" · {brl(a.get('preco'))}" if a.get("preco") else ""
            url = html.escape(a.get("url_afiliado") or a["url"])
            botoes += (f'<a href="{url}" style="display:block;background:#2b1a1f;color:#fff;text-decoration:none;'
                       f'padding:14px 18px;border-radius:999px;margin:10px 0;font-weight:600;text-align:center">'
                       f'Comprar na {html.escape(a["loja"])}{preco} →</a>')
        cancelar = self.link_cancelar(token or "")
        rodape = (f'<p style="font-size:12px;color:#9a8a8e;margin-top:24px">Não quer mais este alerta? '
                  f'<a href="{html.escape(cancelar)}" style="color:#9a8a8e">Cancelar</a></p>') if cancelar else ""
        return f"""<!doctype html><html><body style="margin:0;background:#fbf4f1;font-family:Helvetica,Arial,sans-serif">
<div style="max-width:480px;margin:0 auto;padding:32px 20px">
 <div style="background:#fff;border-radius:24px;padding:28px;text-align:center;box-shadow:0 8px 30px rgba(80,30,40,.08)">
  <div style="font-size:13px;letter-spacing:.18em;text-transform:uppercase;color:#c25b72;font-weight:700">Voltou ao estoque</div>
  <h1 style="font-family:Georgia,serif;font-weight:400;color:#2b1a1f;font-size:28px;margin:10px 0 4px">{nome}</h1>
  <div style="color:#7c6a6f;margin-bottom:22px">{marca}</div>
  {img_html}
  {botoes}
  <p style="color:#7c6a6f;font-size:14px">Esses produtos costumam esgotar rápido. Boa sorte! 💕</p>
  {rodape}
 </div>
</div></body></html>"""

    # ------------------------------------------------------------------
    def enviar_email(self, para: str, assunto: str, corpo_html: str, corpo_txt: str) -> tuple[bool, str]:
        if self.seco:
            self.enviados.append({"canal": "email", "para": para, "assunto": assunto, "texto": corpo_txt})
            log.info("[seco] e-mail para %s: %s", para, assunto)
            return True, ""
        if not (self.smtp_user and self.smtp_senha):
            return False, "SMTP não configurado"
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = formataddr((self.remetente, self.smtp_user))
        msg["To"] = para
        msg.set_content(corpo_txt)
        msg.add_alternative(corpo_html, subtype="html")
        try:
            ctx = ssl.create_default_context()
            if self.smtp_porta == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_porta, context=ctx, timeout=30) as s:
                    s.login(self.smtp_user, self.smtp_senha)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_porta, timeout=30) as s:
                    s.starttls(context=ctx)
                    s.login(self.smtp_user, self.smtp_senha)
                    s.send_message(msg)
            return True, ""
        except Exception as e:  # noqa: BLE001
            return False, str(e)[:300]

    def enviar_whatsapp(self, numero: str, texto: str, callmebot_key: str | None,
                        produto: dict | None = None, achados: list[dict] | None = None) -> tuple[bool, str]:
        numero = "".join(ch for ch in (numero or "") if ch.isdigit())
        if not numero:
            return False, "sem número"
        if self.seco:
            self.enviados.append({"canal": "whatsapp", "para": numero, "texto": texto})
            log.info("[seco] WhatsApp para %s", numero)
            return True, ""
        try:
            if callmebot_key:
                r = requests.get("https://api.callmebot.com/whatsapp.php",
                                 params={"phone": "+" + numero, "text": texto, "apikey": callmebot_key},
                                 timeout=40)
                ok = r.status_code == 200 and "error" not in r.text.lower()[:400]
                return ok, "" if ok else r.text[:300]
            if self.meta_token and self.meta_phone_id and self.meta_template and produto and achados:
                a = achados[0]
                corpo = {
                    "messaging_product": "whatsapp", "to": numero, "type": "template",
                    "template": {"name": self.meta_template, "language": {"code": self.meta_lang},
                                 "components": [{"type": "body", "parameters": [
                                     {"type": "text", "text": f"{produto['marca']} {produto['nome']}"[:60]},
                                     {"type": "text", "text": a["loja"]},
                                     {"type": "text", "text": a.get("url_afiliado") or a["url"]}]}]},
                }
                r = requests.post(f"https://graph.facebook.com/v21.0/{self.meta_phone_id}/messages",
                                  json=corpo, headers={"Authorization": f"Bearer {self.meta_token}"}, timeout=30)
                return r.status_code < 300, "" if r.status_code < 300 else r.text[:300]
            return False, "WhatsApp não ativado (falta a chave CallMeBot)"
        except requests.RequestException as e:
            return False, str(e)[:300]

    # ------------------------------------------------------------------
    def avisar(self, produto: dict, inscricao: dict, achados: list[dict]) -> list[dict]:
        """Envia por todos os canais da inscrição. Devolve linhas para a tabela avisos."""
        token = inscricao.get("token")
        lojas = ", ".join(a["loja"] for a in achados)
        assunto = f"💄 Voltou: {produto['marca']} {produto['nome']}" + (f" ({produto['cor']})" if produto.get("cor") else "") + f" — {lojas}"
        txt = self.texto_whatsapp(produto, achados, token)
        resultados = []
        if inscricao.get("email"):
            ok, erro = self.enviar_email(inscricao["email"], assunto, self.html_email(produto, achados, token), txt)
            resultados.append(("email", ok, erro))
        if inscricao.get("whatsapp"):
            ok, erro = self.enviar_whatsapp(inscricao["whatsapp"], txt, inscricao.get("callmebot_key"), produto, achados)
            resultados.append(("whatsapp", ok, erro))
        linhas = []
        for a in achados:
            for canal, ok, erro in resultados:
                linhas.append({"inscricao_id": inscricao["id"], "produto_id": produto["id"], "loja": a["loja"],
                               "canal": canal, "ok": ok, "erro": erro or None})
        for canal, ok, erro in resultados:
            if not ok:
                log.warning("Falha no %s para inscrição %s: %s", canal, inscricao["id"], erro)
        return linhas

    def avisar_admin(self, produto: dict, achados: list[dict]):
        if not (self.admin_email or self.admin_wpp):
            return
        txt = self.texto_whatsapp(produto, achados, None)
        if self.admin_email:
            self.enviar_email(self.admin_email, f"[admin] Voltou: {produto['marca']} {produto['nome']}",
                              self.html_email(produto, achados, None), txt)
        if self.admin_wpp and self.admin_wpp_key:
            self.enviar_whatsapp(self.admin_wpp, txt, self.admin_wpp_key)
