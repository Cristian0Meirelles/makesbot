"use strict";
const el = id => document.getElementById(id);
const cfg = window.VOLTOU_CONFIG;
const chave = "voltou.sessao";
const pendente = "voltou.confirmarEmail";
const retorno = encodeURIComponent(location.origin + location.pathname);
let modo = "entrar";

async function auth(path, body, token, method = "POST") {
  const r = await fetch(cfg.supabaseUrl + "/auth/v1/" + path, {
    method, headers: {apikey: cfg.supabaseAnonKey, Authorization: "Bearer " + (token || cfg.supabaseAnonKey),
      "Content-Type": "application/json"}, body: body && JSON.stringify(body)
  });
  const dados = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(r.status === 429 ? "limite" : dados.error_code || "falha");
  return dados;
}

function abrir(etapa, email = "") {
  modo = etapa;
  const cadastro = etapa === "cadastro";
  el("titulo").textContent = {entrar:"Entrar na minha conta", cadastro:"Criar minha conta", verificar:"Confirme seu e-mail", perfil:"Minha conta"}[etapa];
  el("acesso").hidden = !["cadastro", "entrar"].includes(etapa);
  el("verificacao").hidden = etapa !== "verificar";
  el("perfil").hidden = etapa !== "perfil";
  el("repetir").hidden = !cadastro;
  el("confirmacao").required = cadastro;
  el("senha").autocomplete = cadastro ? "new-password" : "current-password";
  el("senha").minLength = cadastro ? 8 : 1;
  el("enviar").textContent = cadastro ? "Criar conta e verificar e-mail" : "Entrar";
  el("alternar").textContent = cadastro ? "Já tenho conta" : "Criar conta";
  el("mensagem").textContent = "";
  el("senha").value = el("confirmacao").value = el("codigo").value = "";
  if (etapa === "perfil") el("identidade").textContent = email;
  if (etapa === "verificar") {
    sessionStorage.setItem(pendente, email);
    el("destino").textContent = email;
    el("codigo").focus();
  }
}

async function sessao(token) {
  const user = await auth("user", null, token, "GET");
  if (!user.email_confirmed_at || !user.email) throw new Error("email_not_confirmed");
  sessionStorage.setItem(chave, token);
  sessionStorage.removeItem(pendente);
  abrir("perfil", user.email);
}

async function executar(acao, mensagem) {
  const botoes = document.querySelectorAll("button");
  botoes.forEach(b => b.disabled = true);
  el("mensagem").textContent = "";
  try { await acao(); }
  catch (e) { el("mensagem").textContent = e.message === "limite" ? "Muitas tentativas. Aguarde alguns minutos antes de tentar novamente." : mensagem; }
  finally { botoes.forEach(b => b.disabled = false); }
}

el("alternar").onclick = () => abrir(modo === "entrar" ? "cadastro" : "entrar");
el("voltar").onclick = () => { sessionStorage.removeItem(pendente); abrir("entrar"); };
el("acesso").onsubmit = e => {
  e.preventDefault();
  const email = el("email").value.trim(), password = el("senha").value;
  if (modo === "cadastro" && password !== el("confirmacao").value) {
    el("mensagem").textContent = "As senhas precisam ser iguais."; el("confirmacao").focus(); return;
  }
  executar(async () => {
    if (modo === "cadastro") {
      await auth("signup?redirect_to=" + retorno, {email, password});
      abrir("verificar", email);
    } else {
      try {
        const dados = await auth("token?grant_type=password", {email, password});
        await sessao(dados.access_token);
      } catch (e) {
        if (e.message !== "email_not_confirmed") throw e;
        abrir("verificar", email);
      }
    }
  }, modo === "cadastro" ? "Não foi possível iniciar o cadastro. Confira os dados e tente novamente." : "Não foi possível entrar. Confira seu e-mail e senha.");
};
el("verificacao").onsubmit = e => {
  e.preventDefault();
  executar(async () => {
    const dados = await auth("verify", {email: sessionStorage.getItem(pendente), token: el("codigo").value.trim(), type:"signup"});
    await sessao(dados.access_token);
  }, "Não foi possível confirmar o código. Confira os dígitos ou solicite um novo e-mail.");
};
el("reenviar").onclick = () => executar(async () => {
  await auth("resend?redirect_to=" + retorno, {type:"signup", email:sessionStorage.getItem(pendente)});
  el("mensagem").textContent = "Se a confirmação estiver pendente, confira sua caixa de entrada e o spam.";
}, "Não foi possível reenviar agora.");
el("sair").onclick = () => executar(async () => {
  const token = sessionStorage.getItem(chave);
  sessionStorage.removeItem(chave); abrir("entrar");
  await auth("logout?scope=local", null, token);
}, "Sessão local encerrada.");
async function iniciar() {
  const fragmento = new URLSearchParams(location.hash.slice(1));
  const token = fragmento.get("access_token") || sessionStorage.getItem(chave);
  if (location.hash) history.replaceState(null, "", location.pathname);
  if (token) {
    try { await sessao(token); return; } catch { sessionStorage.removeItem(chave); }
  }
  const email = sessionStorage.getItem(pendente);
  if (email) abrir("verificar", email);
}
iniciar();
