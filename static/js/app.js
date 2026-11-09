// Comportamentos globais do FolhaWeb (sem dependências).
(function () {
  // Confirmação antes de ações importantes: <form data-confirmar="Texto">
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    var msg = form.getAttribute("data-confirmar");
    if (msg && !window.confirm(msg)) { ev.preventDefault(); return; }
    form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (b) {
      b.classList.add("ocupado");
      if (b.dataset.ocupado) b.textContent = b.dataset.ocupado;
    });
  });

  // Menus e popovers: <button data-alternar="id">
  function fecharTodos(excecao) {
    document.querySelectorAll("[data-alternar]").forEach(function (b) {
      var alvo = document.getElementById(b.dataset.alternar);
      if (alvo && alvo !== excecao) { alvo.classList.remove("aberto"); b.setAttribute("aria-expanded", "false"); }
    });
  }
  document.querySelectorAll("[data-alternar]").forEach(function (b) {
    b.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var alvo = document.getElementById(b.dataset.alternar);
      var abrir = !alvo.classList.contains("aberto");
      fecharTodos(alvo);
      alvo.classList.toggle("aberto", abrir);
      b.setAttribute("aria-expanded", String(abrir));
      if (abrir && window.FolhaMovimento) window.FolhaMovimento.surgir(alvo);
    });
  });
  document.addEventListener("click", function (ev) {
    if (!ev.target.closest(".popover, .menu-mais")) fecharTodos(null);
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") { fecharTodos(null); fecharFolha(); }
  });

  // Menu de celular (folha cheia)
  var folha = document.getElementById("folha-movel");
  var botaoMenu = document.querySelector("[data-abrir-menu]");
  function fecharFolha() {
    if (!folha) return;
    folha.classList.remove("aberta");
    if (botaoMenu) botaoMenu.setAttribute("aria-expanded", "false");
  }
  if (botaoMenu && folha) {
    botaoMenu.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var abrir = !folha.classList.contains("aberta");
      folha.classList.toggle("aberta", abrir);
      botaoMenu.setAttribute("aria-expanded", String(abrir));
      if (abrir && window.FolhaMovimento) window.FolhaMovimento.listaEmCascata(folha.querySelectorAll("a, .sec"));
    });
  }

  // Tema claro/escuro (respeita o sistema até o usuário escolher)
  document.querySelectorAll("[data-tema]").forEach(function (b) {
    b.addEventListener("click", function (ev) {
      ev.preventDefault();
      var raiz = document.documentElement;
      var escuroAgora = raiz.dataset.theme ? raiz.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      raiz.dataset.theme = escuroAgora ? "light" : "dark";
      try { localStorage.setItem("tema", raiz.dataset.theme); } catch (e) {}
      document.dispatchEvent(new Event("tema-alterado"));
    });
  });

  // Fila do eSocial: processa automaticamente enquanto houver algo em andamento.
  var caixa = document.getElementById("status-esocial");
  if (!caixa) return;
  var ponto = document.querySelector("[data-ponto-esocial]");
  var urlProcessar = caixa.dataset.processar, urlSituacao = caixa.dataset.situacao;
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
  var recarregar = caixa.dataset.recarregar === "1";
  var ultimo = null;

  function linha(texto, negrito) {
    var d = document.createElement("div");
    if (negrito) { var b = document.createElement("b"); b.textContent = texto; d.appendChild(b); } else d.textContent = texto;
    return d;
  }
  function mostrar(s) {
    var andamento = (s.pendentes || 0) + (s.enviados || 0);
    if (ponto) {
      ponto.classList.toggle("trabalhando", andamento > 0 && !s.erro);
      ponto.classList.toggle("erro", !!s.erro || (s.problemas || 0) > 0);
    }
    var t = caixa.querySelector(".texto");
    t.textContent = "";
    t.appendChild(linha(s.erro ? "eSocial pausado" : andamento ? "Enviando ao eSocial…" : "eSocial em dia", true));
    if (s.erro) t.appendChild(linha(s.erro));
    t.appendChild(linha("Na fila: " + (s.pendentes || 0) + " · Com o governo: " + (s.enviados || 0)));
    t.appendChild(linha("Aceitos: " + (s.aceitos || 0) + (s.problemas ? " · Com erro: " + s.problemas : "")));
    var chave = [s.pendentes, s.enviados, s.aceitos, s.problemas].join("/");
    if (recarregar && ultimo !== null && chave !== ultimo && !andamento) window.location.reload();
    ultimo = chave;
    return andamento > 0 && !s.erro;
  }
  function ciclo() {
    fetch(urlProcessar, { method: "POST", headers: { "X-CSRFToken": csrf }, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (s) { if (mostrar(s)) setTimeout(ciclo, 15000); })
      .catch(function () { setTimeout(ciclo, 30000); });
  }
  fetch(urlSituacao, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (s) {
    if (mostrar(s)) setTimeout(ciclo, 3000);
  });
})();
