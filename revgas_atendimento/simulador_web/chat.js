// Simulador RevGás: chat no estilo WhatsApp ligado ao atendimento de verdade (mesmo banco do servidor).
// Todo texto entra na página por textContent: nada do que o cliente ou o bot escreve vira HTML.
"use strict";

const CHAVE_LOCAL = "revgas-simulador-v1";
const ATRASO_MINIMO_MS = 450; // o "digitando..." aparece um pouquinho, como num chat de verdade
const SUGESTOES = ["oi", "quero gás", "P13", "2", "01001-000", "pix", "sim", "não sei", "cancelar"];
const ESTADO_INICIAL = {
  contatos: [{ telefone: "5511999990001", nome: "Cliente 1" }],
  conversas: {},
  ativo: "5511999990001",
};

const $ = (seletor) => document.querySelector(seletor);
const app = $("#app");
const listaContatos = $("#lista-contatos");
const areaMensagens = $("#mensagens");
const campoTexto = $("#campo-texto");
const botaoEnviar = $("#botao-enviar");

let estado = carregar();
let enviando = false;

// ── Estado guardado só neste navegador (a conversa de verdade fica no servidor) ──
function carregar() {
  try {
    const salvo = JSON.parse(localStorage.getItem(CHAVE_LOCAL) || "null");
    if (salvo && Array.isArray(salvo.contatos) && salvo.contatos.length) {
      salvo.conversas = salvo.conversas || {};
      if (!salvo.contatos.some((c) => c.telefone === salvo.ativo)) salvo.ativo = salvo.contatos[0].telefone;
      return salvo;
    }
  } catch (_) { /* navegador sem armazenamento: começa do zero */ }
  return structuredClone(ESTADO_INICIAL);
}

function salvar() {
  try { localStorage.setItem(CHAVE_LOCAL, JSON.stringify(estado)); } catch (_) { /* sem armazenamento */ }
}

// ── Utilidades ──────────────────────────────────────────────────────────────
function criar(tag, classe, texto) {
  const elemento = document.createElement(tag);
  if (classe) elemento.className = classe;
  if (texto !== undefined) elemento.textContent = texto;
  return elemento;
}

function horaAgora() {
  return new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function normalizarTelefone(texto) {
  let digitos = String(texto).replace(/\D/g, "");
  if (digitos.length === 10 || digitos.length === 11) digitos = "55" + digitos;
  return digitos.length >= 12 && digitos.length <= 13 ? digitos : null;
}

function formatarTelefone(digitos) {
  const d = String(digitos);
  const numero = d.slice(4);
  const meio = numero.length === 9 ? 5 : 4;
  return `+${d.slice(0, 2)} (${d.slice(2, 4)}) ${numero.slice(0, meio)}-${numero.slice(meio)}`;
}

function iniciais(nome) {
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  return ((partes[0] || "?")[0] + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}

function corDoAvatar(telefone) {
  let soma = 0;
  for (const c of telefone) soma = (soma + c.charCodeAt(0)) % 997;
  return `avatar avatar--c${soma % 6}`;
}

function iconeVisto(lido) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 11");
  svg.setAttribute("class", lido ? "visto visto--lido" : "visto");
  svg.setAttribute("aria-label", lido ? "lida" : "enviada");
  const caminho = document.createElementNS("http://www.w3.org/2000/svg", "path");
  caminho.setAttribute("d", "M11.1.6 4.8 7 2.2 4.4 1 5.6l3.8 3.8L12.3 1.8zm3.9 0L8.7 7 8 6.3 6.8 7.5l1.9 1.9L16.2 1.8z");
  svg.appendChild(caminho);
  return svg;
}

const contatoAtivo = () => estado.contatos.find((c) => c.telefone === estado.ativo);
const conversaAtiva = () => (estado.conversas[estado.ativo] ||= []);

// ── Lista de contatos ───────────────────────────────────────────────────────
function desenharContatos() {
  listaContatos.replaceChildren();
  for (const contato of estado.contatos) {
    const ultima = (estado.conversas[contato.telefone] || []).at(-1);
    const botao = criar("button", "contato");
    botao.type = "button";
    if (contato.telefone === estado.ativo) botao.setAttribute("aria-current", "true");
    botao.addEventListener("click", () => abrirConversa(contato.telefone));

    const linha = criar("span", "contato__linha");
    linha.append(criar("span", "contato__nome", contato.nome), criar("span", "contato__hora", ultima ? ultima.hora : ""));
    const previa = ultima ? (ultima.de === "cliente" ? "Você: " : "") + ultima.texto.split("\n")[0] : formatarTelefone(contato.telefone);
    const texto = criar("span", "contato__texto");
    texto.append(linha, criar("span", "contato__previa", previa));

    botao.append(criar("span", corDoAvatar(contato.telefone), iniciais(contato.nome)), texto);
    const item = criar("li");
    item.append(botao);
    listaContatos.append(item);
  }
}

// ── Mensagens ───────────────────────────────────────────────────────────────
function desenharMensagens() {
  areaMensagens.replaceChildren(
    criar("div", "dia", "Hoje"),
    criar("div", "aviso-inicial",
      "Simulação local: as respostas aparecem só aqui, nada é enviado ao WhatsApp. " +
      "Cadastros e pedidos ficam gravados no banco do servidor.")
  );
  let anterior = null;
  for (const mensagem of conversaAtiva()) {
    areaMensagens.append(criarBalao(mensagem, !anterior || anterior.de !== mensagem.de));
    anterior = mensagem;
  }
  rolarParaOFim();
}

function criarBalao(mensagem, novoGrupo) {
  const balao = criar("div", `balao balao--${mensagem.de}${novoGrupo ? " balao--novo-grupo" : ""}`);
  balao.append(document.createTextNode(mensagem.texto));
  if (mensagem.de !== "sistema") {
    const meta = criar("span", "balao__meta", mensagem.hora);
    if (mensagem.de === "cliente") meta.append(iconeVisto(Boolean(mensagem.lida)));
    balao.append(meta);
  }
  return balao;
}

function mostrarDigitando(sim) {
  $("#digitando")?.remove();
  $("#status-bot").replaceChildren();
  if (sim) {
    const balao = criar("div", "balao balao--bot balao--novo-grupo");
    balao.id = "digitando";
    const pontos = criar("span", "digitando");
    pontos.setAttribute("aria-label", "digitando");
    pontos.append(criar("span"), criar("span"), criar("span"));
    balao.append(pontos);
    areaMensagens.append(balao);
    $("#status-bot").textContent = "digitando…";
    rolarParaOFim();
  } else {
    $("#status-bot").append("conversando como ", criar("strong", "", contatoAtivo()?.nome || ""));
  }
}

function rolarParaOFim() {
  areaMensagens.scrollTop = areaMensagens.scrollHeight;
}

function adicionar(telefone, mensagem) {
  (estado.conversas[telefone] ||= []).push(mensagem);
  salvar();
}

// ── Conversa com o servidor do simulador ────────────────────────────────────
async function postar(caminho, corpo) {
  const resposta = await fetch(caminho, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    throw new Error(typeof dados.detail === "string" ? dados.detail : `erro ${resposta.status}`);
  }
  return dados;
}

const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

async function enviar(texto) {
  texto = texto.trim();
  if (!texto || enviando) return;
  const telefone = estado.ativo;
  enviando = true;
  botaoEnviar.disabled = true;
  adicionar(telefone, { de: "cliente", texto, hora: horaAgora(), lida: false });
  desenharMensagens();
  desenharContatos();
  mostrarDigitando(true);
  try {
    const [dados] = await Promise.all([postar("/api/mensagem", { telefone, texto }), esperar(ATRASO_MINIMO_MS)]);
    for (const mensagem of estado.conversas[telefone]) mensagem.lida = true;
    adicionar(telefone, { de: "bot", texto: dados.resposta, hora: horaAgora() });
  } catch (erro) {
    adicionar(telefone, { de: "sistema", texto: `Não consegui falar com o simulador (${erro.message}). Ele está rodando?` });
  } finally {
    enviando = false;
    botaoEnviar.disabled = false;
    mostrarDigitando(false);
    if (telefone === estado.ativo) desenharMensagens();
    desenharContatos();
    atualizarPainel();
  }
}

// ── Painel "No sistema" ─────────────────────────────────────────────────────
function campo(rotulo, valor) {
  const bloco = criar("div", "campo");
  bloco.append(criar("span", "campo__rotulo", rotulo), criar("span", "", valor));
  return bloco;
}

async function atualizarPainel() {
  const telefone = estado.ativo;
  const cadastroEl = $("#painel-cadastro");
  const pedidosEl = $("#painel-pedidos");
  try {
    const dados = await postar("/api/cliente", { telefone });
    if (telefone !== estado.ativo) return; // trocou de conversa enquanto carregava
    cadastroEl.replaceChildren();
    if (dados.cadastro) {
      cadastroEl.append(
        campo("Nome", dados.cadastro.nome),
        campo("Telefone de contato", dados.cadastro.telefone_contato),
        campo("Endereço", dados.cadastro.endereco),
        campo("WhatsApp", formatarTelefone(telefone)),
      );
    } else {
      cadastroEl.append(criar("p", "vazio", `Nenhum cadastro para ${formatarTelefone(telefone)}. Mande "oi" para começar.`));
    }
    pedidosEl.replaceChildren();
    if (!dados.pedidos.length) pedidosEl.append(criar("li", "vazio", 'Nenhum pedido ainda. Mande "quero gás".'));
    for (const pedido of dados.pedidos) {
      const item = criar("li", "pedido");
      const topo = criar("div", "pedido__topo");
      topo.append(criar("span", "pedido__itens", `#${pedido.id} · ${pedido.itens}`), criar("span", `selo selo--${pedido.status}`, pedido.status === "CANCELADO" ? "Cancelado" : "Confirmado"));
      const quando = pedido.criado_em ? new Date(pedido.criado_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";
      item.append(
        topo,
        criar("div", "pedido__detalhe", pedido.endereco),
        criar("div", "pedido__detalhe", `Pagamento: ${pedido.pagamento}`),
        criar("div", "pedido__detalhe", quando),
      );
      pedidosEl.append(item);
    }
  } catch (erro) {
    cadastroEl.replaceChildren(criar("p", "vazio", `Não consegui ler os dados (${erro.message}).`));
    pedidosEl.replaceChildren();
  }
}

async function carregarInfo() {
  try {
    const resposta = await fetch("/api/info");
    const info = await resposta.json();
    const prazo = info.prazo_cancelamento_min > 0 ? `${info.prazo_cancelamento_min} min` : "desligado";
    $("#painel-info").textContent =
      `Prazo de cancelamento: ${prazo} · CEP: ${info.cep_online ? "consulta no ViaCEP" : "sem consulta online"} · Dados: ${info.banco}`;
  } catch (_) { /* o rodapé é só informativo */ }
}

// ── Navegação ───────────────────────────────────────────────────────────────
function abrirConversa(telefone) {
  estado.ativo = telefone;
  salvar();
  app.dataset.tela = "chat";
  desenharContatos();
  desenharMensagens();
  mostrarDigitando(false);
  atualizarPainel();
  campoTexto.focus();
}

function alternarPainel(abrir) {
  app.dataset.painel = abrir ? "aberto" : "";
  $("#botao-painel").setAttribute("aria-expanded", String(abrir));
}

function desenharSugestoes() {
  const area = $("#sugestoes");
  for (const sugestao of SUGESTOES) {
    const botao = criar("button", "sugestao", sugestao);
    botao.type = "button";
    botao.addEventListener("click", () => enviar(sugestao));
    area.append(botao);
  }
}

function ajustarAltura() {
  campoTexto.style.height = "auto";
  campoTexto.style.height = `${Math.min(campoTexto.scrollHeight, 140)}px`;
}

// ── Eventos ─────────────────────────────────────────────────────────────────
$("#compositor").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const texto = campoTexto.value;
  campoTexto.value = "";
  ajustarAltura();
  enviar(texto);
});

campoTexto.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter" && !evento.shiftKey && !evento.isComposing) {
    evento.preventDefault();
    $("#compositor").requestSubmit();
  }
});
campoTexto.addEventListener("input", ajustarAltura);

$("#botao-novo").addEventListener("click", () => {
  const form = $("#form-novo");
  form.hidden = !form.hidden;
  $("#botao-novo").setAttribute("aria-expanded", String(!form.hidden));
  if (!form.hidden) $("#novo-nome").focus();
});

$("#novo-cancelar").addEventListener("click", () => {
  $("#form-novo").hidden = true;
  $("#botao-novo").setAttribute("aria-expanded", "false");
});

$("#form-novo").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const telefone = normalizarTelefone($("#novo-telefone").value);
  const erro = $("#novo-erro");
  if (!telefone) {
    erro.textContent = "Use DDD + número, ex.: 11 99999-0002.";
    return;
  }
  if (!estado.contatos.some((c) => c.telefone === telefone)) {
    const nome = $("#novo-nome").value.trim() || `Cliente ${estado.contatos.length + 1}`;
    estado.contatos.unshift({ telefone, nome: nome.slice(0, 40) });
  }
  erro.textContent = "";
  evento.target.reset();
  evento.target.hidden = true;
  $("#botao-novo").setAttribute("aria-expanded", "false");
  abrirConversa(telefone);
});

$("#botao-limpar").addEventListener("click", () => {
  estado.conversas[estado.ativo] = [];
  salvar();
  desenharMensagens();
  desenharContatos();
});

$("#botao-voltar").addEventListener("click", () => { app.dataset.tela = "contatos"; });
$("#botao-painel").addEventListener("click", () => alternarPainel(app.dataset.painel !== "aberto"));
$("#botao-fechar-painel").addEventListener("click", () => alternarPainel(false));

// ── Início ──────────────────────────────────────────────────────────────────
desenharSugestoes();
carregarInfo();
abrirConversa(estado.ativo);
