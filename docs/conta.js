"use strict";
const el = id => document.getElementById(id);
const cfg = window.VOLTOU_CONFIG;
const chave = "voltou.sessao";
async function auth(path, token, body, method = "POST") {
  const r = await fetch(cfg.supabaseUrl + "/auth/v1/" + path, {
    method, headers: {apikey: cfg.supabaseAnonKey, Authorization: "Bearer " + (token || cfg.supabaseAnonKey),
      "Content-Type": "application/json"}, body: body && JSON.stringify(body)
  });
  if (!r.ok) throw new Error(String(r.status));
  return r.status === 204 ? null : r.text().then(t => t ? JSON.parse(t) : null);
}
function mostrar(email) {
  el("identidade").textContent = email || "";
  el("perfil").hidden = !email;
  el("acesso").hidden = !!email;
}
async function iniciar() {
  const token = sessionStorage.getItem(chave);
  if (token) {
    try { mostrar((await auth("user", token, undefined, "GET")).email); }
    catch { sessionStorage.removeItem(chave); }
  }
}
el("acesso").onsubmit = async e => {
  e.preventDefault();
  const cadastro = e.submitter?.value === "cadastrar";
  const password = el("senha").value;
  if (cadastro && password.length < 8) {
    el("mensagem").textContent = "Use uma senha de pelo menos oito caracteres."; return;
  }
  const botoes = el("acesso").querySelectorAll("button");
  botoes.forEach(b => b.disabled = true);
  try {
    const dados = await auth(cadastro ? "signup" : "token?grant_type=password", null,
      {email: el("email").value.trim(), password});
    el("senha").value = "";
    if (dados.access_token && dados.user?.email) {
      sessionStorage.setItem(chave, dados.access_token); mostrar(dados.user.email);
      el("mensagem").textContent = "Sessão iniciada.";
    } else el("mensagem").textContent = "Confira seu e-mail para confirmar o cadastro e depois entre com sua senha.";
  } catch (erro) {
    el("mensagem").textContent = erro.message === "429" ? "Muitas tentativas. Aguarde alguns minutos."
      : cadastro ? "Não foi possível criar a conta. Confira o e-mail e a senha." : "Não foi possível entrar. Confira suas credenciais e a confirmação do e-mail.";
  } finally { botoes.forEach(b => b.disabled = false); }
};
el("sair").onclick = async () => {
  const token = sessionStorage.getItem(chave);
  sessionStorage.removeItem(chave); mostrar(null); el("mensagem").textContent = "Você saiu desta sessão.";
  try { await auth("logout?scope=local", token); } catch { /* sessão local encerrada */ }
};
iniciar();
